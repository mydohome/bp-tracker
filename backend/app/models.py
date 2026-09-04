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

    gross_pay = Column(Float, nullable=False, default=0)      # lordo
    net_pay = Column(Float, nullable=False, default=0)        # netto
    reimbursements = Column(Float, nullable=False, default=0) # rimborsi spese
    total_deductions = Column(Float, nullable=False, default=0)  # trattenute/contributi/IRPEF

    earnings_detail = Column(JSON, nullable=True)     # [{label, amount}, ...]
    deductions_detail = Column(JSON, nullable=True)   # [{label, amount}, ...]

    notes = Column(String, nullable=True)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())
