import os
import json
import re
import time
from anthropic import Anthropic, APIError, RateLimitError, APIConnectionError

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")

_client = None


def get_client() -> Anthropic:
    global _client
    if _client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY non impostata. Aggiungila al file .env prima di avviare docker compose."
            )
        _client = Anthropic(api_key=api_key)
    return _client


EXTRACTION_SYSTEM_PROMPT = """Sei un motore di estrazione dati per buste paga italiane.
Ricevi il testo (già anonimizzato: nome, codice fiscale, indirizzo e IBAN sono
già stati rimossi) di UNA busta paga.

Leggi TUTTO il testo con attenzione, incluse le righe in fondo al cedolino,
le voci accessorie e le eventuali sezioni "dati per il conguaglio", "elementi
non ricorrenti", "trasferte", "note spese": spesso i rimborsi sono elencati
separatamente dal corpo principale delle competenze.

Cerca ESPLICITAMENTE voci che indicano un rimborso, anche parziale, tra cui
(elenco non esaustivo, cerca varianti simili e abbreviazioni):
- "rimborso spese", "rimb. spese", "note spese"
- "trasferta", "indennità di trasferta", "indennità trasferta estero"
- "diaria", "diaria forfettaria"
- "rimborso chilometrico", "rimborso km", "indennità chilometrica"
- "rimborso pasti", "buoni pasto" solo se pagati in busta come importo (non il valore del ticket)
- "anticipo spese", "rimborso spese sostenute"
- "rimborsi da 730", "conguaglio 730", "conguaglio fiscale" (il rimborso IRPEF
  derivante dalla dichiarazione dei redditi, erogato tramite busta paga: va
  trattato come rimborso, non come componente ordinaria dello stipendio)

Ogni voce di questo tipo trovata nel documento va:
1) inclusa in "earnings_detail" con la sua etichetta originale e il suo importo;
2) sommata nel campo "reimbursements".

Se non trovi nessuna voce di questo tipo, usa "reimbursements": 0 — ma prima
di concludere che sono assenti, ricontrolla l'intero testo una seconda volta.

Cerca inoltre questi dati, tipicamente riportati nell'intestazione o nel
riepilogo delle competenze fisse del cedolino:

- RAL (Retribuzione Annua Lorda): spesso indicata in alto nel cedolino
  come "RAL", "Retribuzione annua lorda", "Retribuzione annua", talvolta
  vicino al livello di inquadramento. È un importo annuale, non mensile.
- Paga base / minimo contrattuale / minimo tabellare: la voce fissa di
  base della retribuzione lorda (esclusi scatti, superminimi, ecc.).
- Contingenza (indennità di contingenza): spesso assente nei CCNL più
  recenti perché assorbita nella paga base — se non la trovi, usa 0.
- Scatti di anzianità (o "scatti maturati"): importo degli scatti, se
  presenti come voce separata.

Rispondi SOLO con un oggetto JSON valido, senza markdown, senza testo prima o dopo,
con questa struttura esatta:

{
  "year": <int, anno del cedolino>,
  "month": <int 1-12, mese del cedolino>,
  "employer_label": <string breve e generica, es. "Azienda" o il nome societario se presente, altrimenti null>,
  "gross_pay": <float, totale competenze lorde del mese>,
  "net_pay": <float, netto ESATTAMENTE come riportato sul cedolino (es. "netto a pagare"/"netto in busta"), SENZA sottrarre nulla: se il cedolino include i rimborsi nel netto finale, riporta quel valore così com'è>,
  "reimbursements": <float, somma di tutte le voci di rimborso/trasferta/diaria individuate, 0 se davvero assenti>,
  "total_deductions": <float, totale trattenute/contributi/IRPEF>,
  "ral": <float, Retribuzione Annua Lorda se indicata nel documento, altrimenti null>,
  "base_pay": <float, paga base/minimo contrattuale, altrimenti null>,
  "contingenza": <float, indennità di contingenza, 0 se assente/assorbita>,
  "scatti": <float, scatti di anzianità, 0 se assenti>,
  "earnings_detail": [{"label": <string>, "amount": <float>}, ...],
  "deductions_detail": [{"label": <string>, "amount": <float>}, ...]
}

Se un valore non è presente nel testo usa 0 o null. Non inventare importi.
"""


def _strip_json_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    return text


def _extract_json_object(text: str) -> str:
    """
    Isola l'oggetto JSON dal testo di risposta, anche se il modello ha
    aggiunto del testo prima/dopo (es. "Ecco i dati:" oppure una nota finale).
    Prende tutto ciò che va dalla prima '{' all'ultima '}' nel testo.
    """
    cleaned = _strip_json_fences(text)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("Nessun oggetto JSON individuabile nella risposta del modello.")
    return cleaned[start : end + 1]


def _call_and_parse(anonymized_text: str, max_tokens: int) -> tuple[dict, str]:
    client = get_client()
    response = client.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        system=EXTRACTION_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": anonymized_text}],
    )
    text = "".join(
        block.text for block in response.content if getattr(block, "type", None) == "text"
    )
    if not text.strip():
        raise ValueError("Il modello ha restituito una risposta vuota.")

    json_str = _extract_json_object(text)
    data = json.loads(json_str)  # può sollevare json.JSONDecodeError
    return data, response.stop_reason


def extract_payslip_data(anonymized_text: str) -> dict:
    """
    Estrae i dati strutturati dalla busta paga, con tentativi automatici in
    caso di risposta troncata, JSON malformato o risposta vuota (transitori,
    capitano occasionalmente con le chiamate API).
    """
    last_error = None
    max_tokens = 2000

    for attempt in range(3):
        try:
            data, stop_reason = _call_and_parse(anonymized_text, max_tokens)
            if stop_reason == "max_tokens":
                # La risposta è stata tagliata: probabile JSON incompleto.
                # Riprova con un budget di token più alto.
                max_tokens = min(max_tokens * 2, 8000)
                last_error = ValueError("Risposta troncata per limite di token, riprovo con più spazio.")
                continue
            return data
        except (json.JSONDecodeError, ValueError) as e:
            last_error = e
            max_tokens = min(max_tokens * 2, 8000)
            continue
        except RateLimitError as e:
            last_error = e
            time.sleep(2 * (attempt + 1))  # backoff progressivo: 2s, 4s, 6s
            continue
        except (APIConnectionError, APIError) as e:
            last_error = e
            time.sleep(1 * (attempt + 1))
            continue

    raise RuntimeError(
        f"Impossibile interpretare la risposta del modello dopo {attempt + 1} tentativi: {last_error}"
    )


CHAT_SYSTEM_PROMPT = """Sei un assistente che aiuta l'utente ad analizzare lo storico
delle proprie buste paga. Ti vengono forniti solo dati economici aggregati
(nessun dato anagrafico: niente nomi, codici fiscali o indirizzi).
Rispondi in italiano, in modo chiaro e sintetico, basandoti solo sui dati forniti.
Se i dati non bastano per rispondere, dillo esplicitamente.
"""


def ask_about_payslips(question: str, payslips_summary: list) -> str:
    client = get_client()
    context = json.dumps(payslips_summary, ensure_ascii=False)
    response = client.messages.create(
        model=MODEL,
        max_tokens=1000,
        system=CHAT_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"Dati storici delle buste paga (JSON):\n{context}\n\nDomanda: {question}",
            }
        ],
    )
    return "".join(
        block.text for block in response.content if getattr(block, "type", None) == "text"
    )
