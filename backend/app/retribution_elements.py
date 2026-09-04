"""
Analizza le voci grezze del riquadro "Elementi della retribuzione" (o
equivalente) estratte dal cedolino, per riconoscere in modo deterministico
minimo/paga base, contingenza e scatti di anzianità — senza dover chiedere
al modello di categorizzarle (più economico e più affidabile, perché le
etichette esatte variano da un software paghe all'altro, ma i pattern
restano riconoscibili).
"""
import re

BASE_PAY_KEYWORDS = re.compile(r"minimo|paga\s*base", re.IGNORECASE)
CONTINGENZA_KEYWORDS = re.compile(r"conting", re.IGNORECASE)
SCATTI_KEYWORDS = re.compile(r"scatt", re.IGNORECASE)


def parse_elementi_retribuzione(elementi: list) -> dict:
    """
    Ritorna {"base_pay": ..., "contingenza": ..., "scatti": ...} (None se
    la relativa voce non è presente in questo cedolino).
    """
    base_pay = None
    contingenza = None
    scatti = None

    for item in elementi or []:
        label = str(item.get("label", ""))
        amount = float(item.get("amount") or 0)

        if BASE_PAY_KEYWORDS.search(label):
            base_pay = (base_pay or 0) + amount
        elif CONTINGENZA_KEYWORDS.search(label):
            contingenza = (contingenza or 0) + amount
        elif SCATTI_KEYWORDS.search(label):
            scatti = (scatti or 0) + amount

    return {
        "base_pay": round(base_pay, 2) if base_pay is not None else None,
        "contingenza": round(contingenza, 2) if contingenza is not None else None,
        "scatti": round(scatti, 2) if scatti is not None else None,
    }


def calculate_ral(elementi_totale: float | None, mensilita: int) -> float | None:
    """
    RAL = totale mensile del riquadro "Elementi della retribuzione" ×
    numero di mensilità annue (di norma 13, talvolta 14, a seconda del CCNL).
    Puro calcolo, nessuna chiamata AI: gratuito e deterministico.
    """
    if not elementi_totale:
        return None
    return round(elementi_totale * mensilita, 2)
