from sqlalchemy import Column, Integer, Float, String, JSON, DateTime, UniqueConstraint
from sqlalchemy.sql import func
from .database import Base


class Payslip(Base):
    """
    Stores ONLY the economic data extracted from a payslip.
    No name, no codice fiscale, no address, no IBAN, no employee ID
    is ever persisted here - those are stripped before the document
    ever leaves this server (see anonymizer.py).
    """

    __tablename__ = "payslips"
    __table_args__ = (UniqueConstraint("year", "month", name="uq_year_month"),)

    id = Column(Integer, primary_key=True, index=True)
    year = Column(Integer, nullable=False, index=True)
    month = Column(Integer, nullable=False, index=True)  # 1-12

    employer_label = Column(String, nullable=True)  # e.g. "Azienda A" - generic, not personal

    gross_pay = Column(Float, nullable=False, default=0)      # lordo totale del mese

    # net_pay = netto ESCLUSI i rimborsi (solo componente retributiva netta).
    # net_pay_stated = netto così come riportato letteralmente sul cedolino
    # (di norma include eventuali rimborsi/trasferte aggiunti al netto a
    # pagare). Teniamo entrambi per trasparenza: net_pay = net_pay_stated - reimbursements.
    net_pay = Column(Float, nullable=False, default=0)
    net_pay_stated = Column(Float, nullable=True)

    reimbursements = Column(Float, nullable=False, default=0) # rimborsi spese (totale)
    reimbursements_breakdown = Column(JSON, nullable=True)    # [{"category": nome, "amount": float}, ...]
    total_deductions = Column(Float, nullable=False, default=0)  # trattenute/contributi/IRPEF

    # RAL (Retribuzione Annua Lorda) indicata nel cedolino (di solito in alto/intestazione).
    ral = Column(Float, nullable=True)

    # Componenti fisse della retribuzione lorda, tracciate separatamente
    # per seguirne l'andamento nel tempo (aumenti di minimo, scatti maturati, ecc.)
    base_pay = Column(Float, nullable=True)      # paga base / minimo contrattuale
    contingenza = Column(Float, nullable=True)   # indennità di contingenza
    scatti = Column(Float, nullable=True)        # scatti di anzianità

    earnings_detail = Column(JSON, nullable=True)     # [{label, amount}, ...]
    deductions_detail = Column(JSON, nullable=True)   # [{label, amount}, ...]

    notes = Column(String, nullable=True)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())


class ReimbursementCategory(Base):
    """
    Categoria di rimborso configurabile dall'utente (es. "Rimborsi da 730",
    "Rimborso spese"). Ogni voce estratta da un cedolino viene confrontata
    con "codes" (codice voce, es. "F00880") e "keywords" (sottostringhe
    nell'etichetta) per essere assegnata a una categoria.
    """

    __tablename__ = "reimbursement_categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)
    codes = Column(JSON, nullable=True, default=list)     # es. ["F00880"]
    keywords = Column(JSON, nullable=True, default=list)  # es. ["rimborso spese", "note spese"]
    created_at = Column(DateTime(timezone=True), server_default=func.now())
