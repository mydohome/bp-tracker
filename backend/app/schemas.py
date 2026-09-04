from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime


class LineItem(BaseModel):
    label: str
    amount: float


class PayslipOut(BaseModel):
    id: int
    year: int
    month: int
    employer_label: Optional[str] = None
    gross_pay: float
    net_pay: float
    reimbursements: float
    total_deductions: float
    earnings_detail: Optional[List[Dict[str, Any]]] = None
    deductions_detail: Optional[List[Dict[str, Any]]] = None
    notes: Optional[str] = None
    uploaded_at: datetime

    class Config:
        from_attributes = True


class TrendPoint(BaseModel):
    year: int
    month: int
    gross_pay: float
    net_pay: float
    reimbursements: float


class ChatRequest(BaseModel):
    question: str


class ChatResponse(BaseModel):
    answer: str
