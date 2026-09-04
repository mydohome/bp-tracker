"""
Rete di sicurezza lato codice: rilegge le voci estratte (earnings_detail)
cercando parole chiave tipiche dei rimborsi nelle buste paga italiane.
Se il modello ha sottostimato il campo "reimbursements" rispetto a quanto
risulta sommando le voci con queste etichette, usiamo il valore più alto
(più cautelativo: meglio segnalare un rimborso in più da verificare che
perderne uno).
"""
import re

REIMBURSEMENT_KEYWORDS = re.compile(
    r"rimb\w*|trasfert|diari[ae]|indennit.*(trasfert|chilometr|\bkm\b)|"
    r"note\s*spese|nota\s*spese|anticipo\s*spese",
    re.IGNORECASE,
)


def detect_reimbursements(earnings_detail: list) -> tuple[float, list]:
    """
    Ritorna (totale_rilevato, voci_corrispondenti) scansionando earnings_detail
    per etichette che sembrano rimborsi.
    """
    total = 0.0
    matched = []
    for item in earnings_detail or []:
        label = str(item.get("label", ""))
        amount = item.get("amount") or 0
        if REIMBURSEMENT_KEYWORDS.search(label):
            total += float(amount)
            matched.append(label)
    return round(total, 2), matched


def reconcile_reimbursements(extracted_value: float, earnings_detail: list) -> tuple[float, str | None]:
    """
    Confronta il valore estratto dal modello con quello rilevato via keyword.
    Se il rilevamento via keyword trova di più, lo preferisce e restituisce
    anche una nota da mostrare all'utente per trasparenza.
    """
    detected_total, matched_labels = detect_reimbursements(earnings_detail)
    if detected_total > (extracted_value or 0):
        note = (
            f"Rimborsi corretti automaticamente da €{extracted_value:.2f} a €{detected_total:.2f} "
            f"in base alle voci: {', '.join(matched_labels)}."
        )
        return detected_total, note
    return extracted_value, None
