"""
Rimuove i dati personali dal testo estratto dal PDF PRIMA che venga
inviato a qualsiasi servizio esterno (Claude API).

Cosa viene rimosso:
- Codice fiscale (persona fisica)
- Partita IVA
- IBAN
- Righe etichettate con dati anagrafici (Nome, Cognome, Dipendente,
  Residenza, Indirizzo, Comune, Matricola, Data di nascita, ecc.)
- Numeri di telefono ed email

Il testo "ripulito" viene poi mandato al modello per l'estrazione
degli importi. Nessun dato anagrafico viene mai salvato nel database
né incluso nelle richieste di rete.
"""
import re

CF_REGEX = re.compile(r"\b[A-Za-z]{6}\d{2}[A-Za-z]\d{2}[A-Za-z]\d{3}[A-Za-z]\b")
PIVA_REGEX = re.compile(r"\bIT\s?\d{11}\b")
IBAN_REGEX = re.compile(r"\bIT\d{2}[A-Za-z]\d{22}\b|\bIT\d{2}\s?[A-Za-z0-9\s]{20,30}\b")
EMAIL_REGEX = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_REGEX = re.compile(r"\b(?:\+39\s?)?3\d{2}[\s./-]?\d{6,7}\b")

# Etichette tipiche delle buste paga italiane che precedono dati anagrafici.
# Rimuoviamo l'intera riga quando compare una di queste etichette.
LABELED_LINE_REGEX = re.compile(
    r"^.*\b("
    r"dipendente|cognome|nome|codice\s*fiscale|residen\w*|indirizzo|"
    r"comune|matricola|data\s*di\s*nascita|luogo\s*di\s*nascita|"
    r"provincia|cap|via\s|c\.f\.|dipend\.?\b"
    r")\b.*$",
    re.IGNORECASE | re.MULTILINE,
)


def anonymize_text(raw_text: str) -> str:
    text = raw_text

    text = CF_REGEX.sub("[CF_RIMOSSO]", text)
    text = PIVA_REGEX.sub("[PIVA_RIMOSSA]", text)
    text = IBAN_REGEX.sub("[IBAN_RIMOSSO]", text)
    text = EMAIL_REGEX.sub("[EMAIL_RIMOSSA]", text)
    text = PHONE_REGEX.sub("[TELEFONO_RIMOSSO]", text)
    text = LABELED_LINE_REGEX.sub("[RIGA_ANAGRAFICA_RIMOSSA]", text)

    return text
