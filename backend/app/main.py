from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import extract
from typing import List

from . import models, schemas
from .database import engine, get_db, Base, SessionLocal
from .pdf_extract import extract_text_from_pdf
from .anonymizer import anonymize_text
from .zucchetti_format import strip_boilerplate_noise
from .claude_client import extract_payslip_data, ask_about_payslips
from .reimbursement_check import reconcile_reimbursements
from .retribution_elements import parse_elementi_retribuzione, calculate_ral
from .migrations import run_migrations

Base.metadata.create_all(bind=engine)
run_migrations(engine)


def seed_default_reimbursement_categories():
    """
    Alla prima esecuzione, pre-carica le categorie di rimborso più comuni.
    L'utente può poi modificarle/aggiungerne altre dalle impostazioni.
    Non fa nulla se esistono già categorie (non sovrascrive personalizzazioni).
    """
    db = SessionLocal()
    try:
        if db.query(models.ReimbursementCategory).count() > 0:
            return
        defaults = [
            models.ReimbursementCategory(
                name="Rimborsi da 730",
                codes=["F00880"],
                keywords=["rimborsi da 730", "conguaglio 730", "conguaglio fiscale"],
            ),
            models.ReimbursementCategory(
                name="Rimborso spese",
                codes=["000472"],
                keywords=["rimborso spese", "rimb. spese", "note spese", "nota spese", "anticipo spese"],
            ),
        ]
        db.add_all(defaults)
        db.commit()
    finally:
        db.close()


seed_default_reimbursement_categories()

DEFAULT_MENSILITA = "13"  # standard in Italia (12 mensilità + tredicesima)


def get_setting(db: Session, key: str, default: str) -> str:
    row = db.get(models.AppSetting, key)
    return row.value if row else default


def set_setting(db: Session, key: str, value: str) -> None:
    row = db.get(models.AppSetting, key)
    if row:
        row.value = value
    else:
        row = models.AppSetting(key=key, value=value)
        db.add(row)
    db.commit()

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

    # 2b. Rimuove rumore ricorrente (watermark/copyright ripetuti nei
    #     cedolini Zucchetti): riduce i token in input senza perdere dati.
    anonymized = strip_boilerplate_noise(anonymized)

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

    earnings_detail = data.get("earnings_detail") or []
    categories = db.query(models.ReimbursementCategory).all()
    reimbursements, reimbursements_breakdown, reconciliation_note = reconcile_reimbursements(
        float(data.get("reimbursements") or 0), earnings_detail, categories
    )

    # Il modello estrae il netto ESATTAMENTE come riportato sul cedolino
    # (net_pay_stated), che in Italia spesso include i rimborsi/trasferte
    # aggiunti al "netto a pagare". Qui lo scorporiamo: net_pay diventa
    # la sola componente retributiva netta, esclusi i rimborsi.
    net_pay_stated = float(data.get("net_pay") or 0)
    net_pay_salary = round(net_pay_stated - reimbursements, 2)

    # Minimo/contingenza/scatti/RAL vengono ricavati in Python dal riquadro
    # "Elementi della retribuzione" estratto grezzo, NON chiesti al modello:
    # più affidabile (niente hallucination sulla RAL, che raramente è
    # stampata esplicitamente) e più economico in token.
    elementi = data.get("elementi_retribuzione") or []
    elementi_totale = data.get("elementi_retribuzione_totale")
    elementi_totale = float(elementi_totale) if elementi_totale not in (None, "") else None
    parsed_elementi = parse_elementi_retribuzione(elementi)
    mensilita = int(get_setting(db, "mensilita_annue", DEFAULT_MENSILITA))

    record.employer_label = data.get("employer_label")
    record.gross_pay = float(data.get("gross_pay") or 0)
    record.net_pay = net_pay_salary
    record.net_pay_stated = net_pay_stated
    record.reimbursements = reimbursements
    record.reimbursements_breakdown = reimbursements_breakdown
    record.total_deductions = float(data.get("total_deductions") or 0)
    record.ral = calculate_ral(elementi_totale, mensilita)
    record.base_pay = parsed_elementi["base_pay"]
    record.contingenza = parsed_elementi["contingenza"]
    record.scatti = parsed_elementi["scatti"]
    record.elementi_retribuzione = elementi
    record.elementi_retribuzione_totale = elementi_totale
    record.earnings_detail = earnings_detail
    record.deductions_detail = data.get("deductions_detail") or []
    record.notes = reconciliation_note

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
            ral=r.ral,
        )
        for r in records
    ]


@app.get("/api/stats/ral-by-year", response_model=List[schemas.RalYearPoint])
def ral_by_year(db: Session = Depends(get_db)):
    """
    RAL rappresentativa per ciascun anno, per il confronto anno su anno.
    Usa il valore dell'ultimo mese diverso da dicembre quando disponibile:
    se la tredicesima viene caricata insieme al cedolino di dicembre, quel
    mese può riportare nel riquadro "Elementi della retribuzione" un totale
    raddoppiato, che distorcerebbe il calcolo della RAL se usato come
    riferimento. Se per un anno è disponibile solo dicembre, usa comunque
    quel valore (meglio di niente).
    """
    records = (
        db.query(models.Payslip)
        .filter(models.Payslip.ral.isnot(None))
        .order_by(models.Payslip.year.asc(), models.Payslip.month.asc())
        .all()
    )

    by_year: dict[int, dict[int, float]] = {}
    for r in records:
        by_year.setdefault(r.year, {})[r.month] = r.ral

    result = []
    for year in sorted(by_year.keys()):
        months = by_year[year]
        non_december = {m: v for m, v in months.items() if m != 12}
        if non_december:
            source_month = max(non_december.keys())
            ral_value = non_december[source_month]
        else:
            source_month = max(months.keys())
            ral_value = months[source_month]
        result.append(
            schemas.RalYearPoint(year=year, ral=ral_value, source_month=source_month)
        )
    return result


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


# --- Categorie di rimborso (configurabili dall'utente) ---

@app.get("/api/reimbursement-categories", response_model=List[schemas.ReimbursementCategoryOut])
def list_reimbursement_categories(db: Session = Depends(get_db)):
    return (
        db.query(models.ReimbursementCategory)
        .order_by(models.ReimbursementCategory.name.asc())
        .all()
    )


@app.post("/api/reimbursement-categories", response_model=schemas.ReimbursementCategoryOut)
def create_reimbursement_category(
    payload: schemas.ReimbursementCategoryIn, db: Session = Depends(get_db)
):
    name = payload.name.strip()
    if not name:
        raise HTTPException(400, "Il nome della categoria non può essere vuoto.")

    existing = (
        db.query(models.ReimbursementCategory)
        .filter(models.ReimbursementCategory.name == name)
        .first()
    )
    if existing:
        raise HTTPException(409, "Esiste già una categoria con questo nome.")

    codes = [c.strip() for c in (payload.codes or []) if c.strip()]
    keywords = [k.strip() for k in (payload.keywords or []) if k.strip()]
    if not codes and not keywords:
        raise HTTPException(
            400, "Specifica almeno un codice voce o una parola chiave per la categoria."
        )

    category = models.ReimbursementCategory(name=name, codes=codes, keywords=keywords)
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


@app.delete("/api/reimbursement-categories/{category_id}")
def delete_reimbursement_category(category_id: int, db: Session = Depends(get_db)):
    category = db.get(models.ReimbursementCategory, category_id)
    if not category:
        raise HTTPException(404, "Categoria non trovata.")
    db.delete(category)
    db.commit()
    return {"status": "deleted"}


# --- Impostazione mensilità (per il calcolo della RAL) ---

@app.get("/api/settings/mensilita", response_model=schemas.MensilitaOut)
def get_mensilita(db: Session = Depends(get_db)):
    return schemas.MensilitaOut(mensilita=int(get_setting(db, "mensilita_annue", DEFAULT_MENSILITA)))


@app.put("/api/settings/mensilita", response_model=schemas.MensilitaOut)
def update_mensilita(payload: schemas.MensilitaIn, db: Session = Depends(get_db)):
    if payload.mensilita not in (12, 13, 14):
        raise HTTPException(400, "Il numero di mensilità deve essere 12, 13 o 14.")
    set_setting(db, "mensilita_annue", str(payload.mensilita))
    return schemas.MensilitaOut(mensilita=payload.mensilita)


@app.post("/api/recompute-ral")
def recompute_ral(db: Session = Depends(get_db)):
    """
    Ricalcola la RAL di tutte le buste paga già caricate usando il totale
    del riquadro "Elementi della retribuzione" già salvato e la mensilità
    attualmente configurata. Puro calcolo locale: NESSUNA chiamata a Claude,
    quindi gratuito e istantaneo anche su molte buste paga.
    """
    mensilita = int(get_setting(db, "mensilita_annue", DEFAULT_MENSILITA))
    records = db.query(models.Payslip).all()
    updated = 0
    for r in records:
        new_ral = calculate_ral(r.elementi_retribuzione_totale, mensilita)
        if new_ral != r.ral:
            r.ral = new_ral
            updated += 1
    db.commit()
    return {"updated": updated, "total": len(records), "mensilita": mensilita}


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
            "ral": r.ral,
            "base_pay": r.base_pay,
            "contingenza": r.contingenza,
            "scatti": r.scatti,
        }
        for r in records
    ]
    try:
        answer = ask_about_payslips(req.question, summary)
    except Exception as e:
        raise HTTPException(502, f"Errore nella richiesta a Claude: {e}")
    return schemas.ChatResponse(answer=answer)
