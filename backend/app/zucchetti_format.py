"""
Riferimenti sul formato "Cedolino Paga" di Zucchetti S.p.A. (applicativo
Paghe Web), usati per rendere l'estrazione più precisa e più economica in
token quando il documento caricato è in questo formato (molto diffuso in
Italia). Fonte: documento ufficiale Zucchetti S.p.A. "Comprendere il
Cedolino Paga" (aggiornato al 26/03/2014), sezioni 5-8 e 17-18.

Convenzione dei codici voce osservata nella documentazione ufficiale:
- Prefisso "Z" (es. Z00016, Z00020, Z01139): voci retributive variabili
  del mese (Sezione 6) — ferie, festività, straordinari, recuperi, ecc.
- Prefisso "F" (es. F01998, F02000, F09110, F09130): voci fiscali variabili
  del mese (Sezione 8) — imponibile IRPEF, IRPEF lorda/trattenuta,
  addizionali regionali/comunali, conguagli.
- Codici puramente numerici (es. 000323, 000472, 002103): altre voci
  aziendali/contrattuali (trattenute, rimborsi, fringe benefit), specifiche
  dell'azienda/CCNL, non standardizzate a livello nazionale.

Struttura standard del cedolino (rilevante per l'estrazione):
- "ELEMENTI DELLA RETRIBUZIONE": componenti fisse mensili (minimo,
  contingenza, EDR, superminimi...) con riga TOTALE.
- "VOCI VARIABILI DEL MESE": straordinari, ferie, rimborsi, trattenute
  puntuali del mese.
- "TOTALE COMPETENZE" / "TOTALE TRATTENUTE": Sezione 17.
- "NETTO DEL MESE" (talvolta "NETTO A PAGARE"): Sezione 18, importo finale.
"""
import re

# Rumore ricorrente che l'estrazione testo del PDF cattura dal watermark
# laterale dei cedolini Zucchetti (si ripete identico su ogni pagina):
# pura perdita di token se inviato al modello, va rimosso senza alcuna
# perdita di dati economici.
_NOISE_PATTERNS = [
    re.compile(
        r"Modello per procedure della ZUCCHETTI.*?RIPRODUZIONE\s*VIETATA",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(r"Tutti i diritti (sono )?riservati (alla )?Zucchetti[^\n]*", re.IGNORECASE),
]


def is_zucchetti_format(text: str) -> bool:
    """Rilevamento leggero: presente il riquadro standard Zucchetti?"""
    return bool(re.search(r"ELEMENTI\s+DELLA\s+RETRIBUZIONE", text, re.IGNORECASE))


def strip_boilerplate_noise(text: str) -> str:
    """
    Rimuove watermark/note di copyright ripetute (nessun dato economico),
    che occupano token senza aggiungere informazione utile all'estrazione.
    """
    for pattern in _NOISE_PATTERNS:
        text = pattern.sub("", text)
    text = re.sub(r"\n{3,}", "\n\n", text)  # comprimi righe vuote lasciate dalla rimozione
    return text


# Nota compatta aggiunta al prompt SOLO quando il documento è riconosciuto
# come cedolino Zucchetti: dà al modello priori più forti sui codici voce,
# riducendo ambiguità (e quindi tentativi/retry) senza dover elencare ogni
# possibile etichetta come nel prompt generico.
ZUCCHETTI_HINT = """

Nota sul formato: questo documento sembra un cedolino Zucchetti (Paghe Web).
Convenzione codici voce: prefisso "Z" = voci retributive variabili (ferie,
straordinari, recuperi); prefisso "F" = voci fiscali (IRPEF, addizionali
regionali/comunali, conguagli); codici numerici puri = voci aziendali/
contrattuali (trattenute, rimborsi, fringe benefit). Il riquadro "ELEMENTI
DELLA RETRIBUZIONE" contiene le componenti fisse mensili con riga TOTALE."""
