"""
Migrazione minimale e additiva: aggiunge le nuove colonne introdotte
nel tempo, senza toccare i dati già presenti. Pensata per un'app
personale a singolo database, senza bisogno di Alembic.

Sicura da eseguire ad ogni avvio: usa "ADD COLUMN IF NOT EXISTS",
quindi su un database già aggiornato non fa nulla.
"""
from sqlalchemy import text
from sqlalchemy.engine import Engine

NEW_COLUMNS = [
    ("net_pay_stated", "DOUBLE PRECISION"),
    ("ral", "DOUBLE PRECISION"),
    ("base_pay", "DOUBLE PRECISION"),
    ("contingenza", "DOUBLE PRECISION"),
    ("scatti", "DOUBLE PRECISION"),
    ("reimbursements_breakdown", "JSON"),
]


def run_migrations(engine: Engine) -> None:
    with engine.begin() as conn:
        for column_name, column_type in NEW_COLUMNS:
            conn.execute(
                text(f"ALTER TABLE payslips ADD COLUMN IF NOT EXISTS {column_name} {column_type}")
            )
