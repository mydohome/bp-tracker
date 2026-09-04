# Tracker Buste Paga

Web app self-hosted (Docker Compose) per caricare le buste paga in PDF ogni mese
e tenere traccia automaticamente di: importo lordo/netto, rimborsi, andamento
nel tempo e aumenti (variazione mese su mese). Include una chat per fare
domande sui propri dati economici, gestita tramite l'API di Claude (Anthropic).

## Architettura

- **backend**: FastAPI (Python) — estrae il testo dal PDF, lo anonimizza,
  chiama Claude per estrarre i dati strutturati, li salva su Postgres.
- **frontend**: pagina statica (HTML/JS + Chart.js) servita da Nginx.
- **db**: PostgreSQL, con volume persistente.

## Privacy: come vengono trattati i tuoi dati

Il PDF caricato **non viene mai inviato online tal quale**. Il flusso è:

1. Il testo viene estratto dal PDF **localmente**, dentro il container backend.
2. Prima di qualsiasi chiamata a Claude, il testo viene **anonimizzato**:
   vengono rimossi codice fiscale, partita IVA, IBAN, email, numeri di
   telefono e tutte le righe con etichette anagrafiche (nome, cognome,
   indirizzo, residenza, matricola, data/luogo di nascita...) — vedi
   `backend/app/anonymizer.py`.
3. Solo il testo anonimizzato (importi, voci in busta, mese/anno) viene
   inviato all'API Anthropic per l'estrazione strutturata.
4. Nel database **non viene mai salvato** un dato anagrafico: la tabella
   `payslips` contiene solo importi, etichette generiche e date (vedi
   `backend/app/models.py`).
5. Il PDF originale non viene salvato su disco: viene letto in memoria e
   scartato dopo l'elaborazione.
6. La chat "Chiedi a Claude" invia solo gli importi aggregati già salvati
   (mai dati anagrafici) per rispondere alle domande sui trend.

Nota: l'anonimizzazione è basata su pattern/regex (CF, IBAN, etichette di
campo tipiche delle buste paga italiane). È un buon livello di protezione
ma non una garanzia assoluta al 100%: se il tuo cedolino ha un layout
insolito, controlla `backend/app/anonymizer.py` e adatta i pattern se serve.

## Pubblicare il repository su GitHub

Questo pacchetto contiene già un repository Git locale (`git init` + commit iniziale).
Claude non può autenticarsi sul tuo account GitHub, quindi il push va fatto da te
(bastano 3 comandi):

```bash
cd payslip-app
gh repo create payslip-tracker --private --source=. --remote=origin --push
```

Se non usi la `gh` CLI, in alternativa:

```bash
cd payslip-app
git remote add origin git@github.com:<tuo-utente>/payslip-tracker.git
git branch -M main
git push -u origin main
```

(prima crea il repository vuoto su github.com/new, senza README/licenza,
altrimenti il push fallisce per divergenza della history)

## Setup — installazione automatica

Se hai già Docker e Docker Compose funzionanti, usa lo script incluso:

```bash
./install.sh
```

Lo script verifica i prerequisiti, crea `.env` da `.env.example`, ti chiede
la ANTHROPIC_API_KEY e avvia tutto con `docker compose up -d --build`.

### Setup manuale (alternativa)

1. Copia il file di esempio e inserisci la tua chiave API Anthropic
   (la trovi su https://console.anthropic.com):

   ```bash
   cp .env.example .env
   # poi modifica .env e incolla la tua ANTHROPIC_API_KEY
   ```

2. Avvia tutto:

   ```bash
   docker compose up --build
   ```

3. Apri il browser su **http://localhost:8080**

## Aggiornare l'app quando modifichiamo il codice

Ogni volta che il progetto viene aggiornato sul repository GitHub, sulla
macchina dove gira l'app esegui:

```bash
./update.sh
```

Lo script fa `git fetch`/`git pull` dal repository remoto (se ci sono
modifiche locali non committate te lo chiede prima di procedere), poi
ricostruisce e riavvia solo i container interessati con
`docker compose up -d --build`. Il file `.env` (con la tua API key) non è
tracciato da Git e non viene mai toccato dall'aggiornamento.

Il backend è raggiungibile anche direttamente su `http://localhost:8000`
(utile per test con `curl` o Swagger UI su `http://localhost:8000/docs`).

## Uso

- Ogni mese, carica il PDF della busta paga dalla home page.
- L'app riconosce automaticamente mese/anno: se ricarichi lo stesso mese,
  il record viene aggiornato (non duplicato).
- Il grafico mostra l'andamento di lordo, netto e rimborsi nel tempo.
- La tabella mostra la variazione (Δ) del netto rispetto al mese precedente,
  utile per individuare aumenti o tagli.
- Nel box chat puoi chiedere cose come:
  - "Qual è stato il mese con il netto più alto?"
  - "Quanto ho ricevuto di rimborsi nell'ultimo anno?"
  - "C'è stato un aumento negli ultimi 6 mesi?"

## Backup dei dati

I dati sono in un volume Docker (`payslip_db_data`). Per un backup:

```bash
docker exec payslip_db pg_dump -U payslip payslip > backup.sql
```

## Fermare l'app

```bash
docker compose down
```

Per cancellare anche i dati salvati:

```bash
docker compose down -v
```
