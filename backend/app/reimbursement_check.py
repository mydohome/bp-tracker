"""
Classificazione dei rimborsi per categoria + rete di sicurezza lato codice.

Ogni voce estratta da un cedolino (earnings_detail) viene confrontata con
le categorie configurate dall'utente (codice voce e/o parole chiave). Le
voci che sembrano un rimborso ma non corrispondono a nessuna categoria
configurata finiscono in "Altri rimborsi", così nessun rimborso passa
inosservato anche prima di essere categorizzato esplicitamente.
"""
import re

# Rete di sicurezza generica: intercetta qualunque voce che sembri un
# rimborso anche se non corrisponde a nessuna categoria configurata.
GENERIC_REIMBURSEMENT_KEYWORDS = re.compile(
    r"rimb\w*|trasfert|diari[ae]|indennit.*(trasfert|chilometr|\bkm\b)|"
    r"note\s*spese|nota\s*spese|anticipo\s*spese",
    re.IGNORECASE,
)


def _label_matches_category(label: str, category) -> bool:
    label_lower = label.lower()
    for code in (category.codes or []):
        if code and code.lower() in label_lower:
            return True
    for kw in (category.keywords or []):
        if kw and kw.lower() in label_lower:
            return True
    return False


def categorize_reimbursements(earnings_detail: list, categories: list) -> tuple[list, float]:
    """
    Ritorna (breakdown, totale) dove breakdown è una lista
    [{"category": nome, "amount": totale}], scansionando earnings_detail
    e assegnando ogni voce alla prima categoria configurata che corrisponde,
    oppure a "Altri rimborsi" se sembra un rimborso (via parole chiave
    generiche) ma non corrisponde a nessuna categoria specifica.
    """
    totals: dict[str, float] = {}
    for item in earnings_detail or []:
        label = str(item.get("label", ""))
        amount = float(item.get("amount") or 0)

        matched_category = None
        for cat in categories:
            if _label_matches_category(label, cat):
                matched_category = cat.name
                break

        if matched_category:
            totals[matched_category] = totals.get(matched_category, 0) + amount
        elif GENERIC_REIMBURSEMENT_KEYWORDS.search(label):
            totals["Altri rimborsi"] = totals.get("Altri rimborsi", 0) + amount

    breakdown = [{"category": k, "amount": round(v, 2)} for k, v in totals.items()]
    total = round(sum(totals.values()), 2)
    return breakdown, total


def reconcile_reimbursements(
    extracted_value: float, earnings_detail: list, categories: list
) -> tuple[float, list, str | None]:
    """
    Confronta il valore estratto dal modello con la somma calcolata
    classificando le voci per categoria. Se quest'ultima è maggiore
    (il modello ha sottostimato), la preferisce e lo segnala.
    Ritorna sempre il breakdown per categoria, anche quando i due
    valori coincidono, per mostrarlo nell'interfaccia.
    """
    breakdown, detected_total = categorize_reimbursements(earnings_detail, categories)

    if detected_total > (extracted_value or 0):
        parts = ", ".join(f"{b['category']}: €{b['amount']:.2f}" for b in breakdown)
        note = (
            f"Rimborsi corretti automaticamente da €{extracted_value:.2f} "
            f"a €{detected_total:.2f} ({parts})."
        )
        return detected_total, breakdown, note

    return (extracted_value or 0), breakdown, None
