from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import extract
from typing import List

from . import models, schemas
from .database import engine, get_db, Base
from .pdf_extract import extract_text_from_pdf
from .anonymizer import anonymize_text
from .claude_client import extract_payslip_data, ask_about_payslips

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Payslip Tracker")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/upload", response_model=schemas.PayslipOut)
async def upload_payslip(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if file.content_type != "application/pdf" and not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Il file deve essere un PDF.")

    file_bytes = await file.read()

    # 1. Estrai il testo dal PDF (avviene interamente in locale, nel container)
    raw_text = extract_text_from_pdf(file_bytes)
    if not raw_text.strip():
        raise HTTPException(422, "Impossibile estrarre testo dal PDF (potrebbe essere una scansione immagine).")

    # 2. Anonimizza: rimuove nome, CF, indirizzo, IBAN, email, telefono
    #    PRIMA di qualsiasi invio verso l'esterno.
    anonymized = anonymize_text(raw_text)

    # 3. Invia SOLO il testo anonimizzato a Claude per l'estrazione strutturata.
    #    A questo punto raw_text (con i dati personali) esce dallo scope
    #    di questa funzione e non viene mai persistito né inoltrato.
    try:
        data = extract_payslip_data(anonymized)
    except Exception as e:
        raise HTTPException(502, f"Errore nell'interpretazione della busta paga: {e}")

    del raw_text  # esplicito: non serve più, non va salvato da nessuna parte

    year = int(data.get("year") or 0)
    month = int(data.get("month") or 0)
    if not (1 <= month <= 12) or year < 2000:
        raise HTTPException(422, "Non sono riuscito a determinare mese/anno del cedolino.")

    existing = (
        db.query(models.Payslip)
        .filter(models.Payslip.year == year, models.Payslip.month == month)
        .first()
    )

    if existing:
        record = existing
    else:
        record = models.Payslip(year=year, month=month)
        db.add(record)

    record.employer_label = data.get("employer_label")
    record.gross_pay = float(data.get("gross_pay") or 0)
    record.net_pay = float(data.get("net_pay") or 0)
    record.reimbursements = float(data.get("reimbursements") or 0)
    record.total_deductions = float(data.get("total_deductions") or 0)
    record.earnings_detail = data.get("earnings_detail") or []
    record.deductions_detail = data.get("deductions_detail") or []

    db.commit()
    db.refresh(record)
    return record


@app.get("/api/payslips", response_model=List[schemas.PayslipOut])
def list_payslips(db: Session = Depends(get_db)):
    return (
        db.query(models.Payslip)
        .order_by(models.Payslip.year.desc(), models.Payslip.month.desc())
        .all()
    )


@app.get("/api/payslips/{payslip_id}", response_model=schemas.PayslipOut)
def get_payslip(payslip_id: int, db: Session = Depends(get_db)):
    record = db.get(models.Payslip, payslip_id)
    if not record:
        raise HTTPException(404, "Busta paga non trovata.")
    return record


@app.delete("/api/payslips/{payslip_id}")
def delete_payslip(payslip_id: int, db: Session = Depends(get_db)):
    record = db.get(models.Payslip, payslip_id)
    if not record:
        raise HTTPException(404, "Busta paga non trovata.")
    db.delete(record)
    db.commit()
    return {"status": "deleted"}


@app.get("/api/stats/trend", response_model=List[schemas.TrendPoint])
def trend(db: Session = Depends(get_db)):
    records = (
        db.query(models.Payslip)
        .order_by(models.Payslip.year.asc(), models.Payslip.month.asc())
        .all()
    )
    return [
        schemas.TrendPoint(
            year=r.year,
            month=r.month,
            gross_pay=r.gross_pay,
            net_pay=r.net_pay,
            reimbursements=r.reimbursements,
        )
        for r in records
    ]


@app.get("/api/stats/raises")
def raises(db: Session = Depends(get_db)):
    """Confronta ogni mese col mese precedente per evidenziare eventuali aumenti."""
    records = (
        db.query(models.Payslip)
        .order_by(models.Payslip.year.asc(), models.Payslip.month.asc())
        .all()
    )
    result = []
    prev = None
    for r in records:
        delta_net = None
        delta_gross = None
        if prev is not None:
            delta_net = round(r.net_pay - prev.net_pay, 2)
            delta_gross = round(r.gross_pay - prev.gross_pay, 2)
        result.append(
            {
                "year": r.year,
                "month": r.month,
                "net_pay": r.net_pay,
                "gross_pay": r.gross_pay,
                "delta_net": delta_net,
                "delta_gross": delta_gross,
            }
        )
        prev = r
    return result


@app.post("/api/chat", response_model=schemas.ChatResponse)
def chat(req: schemas.ChatRequest, db: Session = Depends(get_db)):
    records = (
        db.query(models.Payslip)
        .order_by(models.Payslip.year.asc(), models.Payslip.month.asc())
        .all()
    )
    # Solo dati economici aggregati, nessun dato anagrafico è mai presente qui.
    summary = [
        {
            "year": r.year,
            "month": r.month,
            "gross_pay": r.gross_pay,
            "net_pay": r.net_pay,
            "reimbursements": r.reimbursements,
            "total_deductions": r.total_deductions,
        }
        for r in records
    ]
    try:
        answer = ask_about_payslips(req.question, summary)
    except Exception as e:
        raise HTTPException(502, f"Errore nella richiesta a Claude: {e}")
    return schemas.ChatResponse(answer=answer)
