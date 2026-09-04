import os
import json
import re
from anthropic import Anthropic

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
Rispondi SOLO con un oggetto JSON valido, senza markdown, senza testo prima o dopo,
con questa struttura esatta:

{
  "year": <int, anno del cedolino>,
  "month": <int 1-12, mese del cedolino>,
  "employer_label": <string breve e generica, es. "Azienda" o il nome societario se presente, altrimenti null>,
  "gross_pay": <float, totale competenze lorde del mese>,
  "net_pay": <float, netto in busta>,
  "reimbursements": <float, totale rimborsi spese/note spese/trasferte, 0 se assenti>,
  "total_deductions": <float, totale trattenute/contributi/IRPEF>,
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


def extract_payslip_data(anonymized_text: str) -> dict:
    client = get_client()
    response = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        system=EXTRACTION_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": anonymized_text}],
    )
    text = "".join(
        block.text for block in response.content if getattr(block, "type", None) == "text"
    )
    cleaned = _strip_json_fences(text)
    return json.loads(cleaned)


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
