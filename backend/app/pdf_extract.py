import io
import pdfplumber


def extract_text_from_pdf(file_bytes: bytes) -> str:
    text_parts = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            text_parts.append(page_text)

            # Estrae anche le tabelle in forma esplicita riga/colonna.
            # Il solo extract_text() a volte "appiattisce" una tabella
            # multi-colonna (es. "Voci variabili del mese": voce, importo
            # base, riferimento, trattenute, competenze) in righe poco
            # chiare, facendo perdere l'associazione tra un'etichetta
            # (es. "Rimborso spese") e l'importo nella colonna corretta.
            # Riportare le tabelle come righe "cella | cella | cella"
            # elimina questa ambiguità per il modello.
            #
            # Primo tentativo: rilevamento basato su linee di tabella
            # (funziona per PDF con bordi/griglie visibili).
            try:
                tables = page.extract_tables()
            except Exception:
                tables = []

            # Fallback: se non trova tabelle con linee, riprova con
            # rilevamento basato sull'allineamento del testo (utile per
            # PDF generati da stampa testuale, senza bordi disegnati).
            if not tables:
                try:
                    tables = page.extract_tables(
                        {"vertical_strategy": "text", "horizontal_strategy": "text"}
                    )
                except Exception:
                    tables = []

            for table in tables:
                rendered_rows = []
                for row in table:
                    cells = [str(c).strip() if c else "" for c in row]
                    if any(cells):
                        rendered_rows.append(" | ".join(cells))
                if rendered_rows:
                    text_parts.append("[TABELLA]\n" + "\n".join(rendered_rows) + "\n[/TABELLA]")

    return "\n".join(text_parts)
