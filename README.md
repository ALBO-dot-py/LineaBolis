# Avvio locale del progetto

Il progetto è pensato per essere eseguito in locale con **Python**, **FastAPI** e **SQLite**. Per riprodurre l'ambiente utilizzato nello sviluppo è sufficiente seguire i passaggi riportati di seguito dalla cartella principale del progetto.

## 1. Prerequisiti

Installare **Python 3.13** da [python.org/downloads](https://www.python.org/downloads/) e gli strumenti da riga di comando di **SQLite** da [sqlite.org/download.html](https://www.sqlite.org/download.html). Al termine verificare dal terminale che i comandi `python` (oppure `py` su Windows) e `sqlite3` siano disponibili.

## 2. Ambiente virtuale e dipendenze

Creare l'ambiente virtuale:

```bash
python -m venv .venv
```

Attivarlo su Windows:

```bash
.venv\Scripts\activate
```

oppure su macOS/Linux:

```bash
source .venv/bin/activate
```

Installare quindi le dipendenze:

```bash
python -m pip install -r requirements.txt
```

## 3. Creazione del database

Il database locale deve chiamarsi **`app.db`**. `schema.sql` crea la struttura, mentre **`seed.sql` è l'unico file utilizzato per caricare i dati dimostrativi**; non è previsto alcun `seed.py`.

```bash
sqlite3 app.db ".read schema.sql"
sqlite3 app.db ".read seed.sql"
```

## 4. Configurazione locale

Prima dell'avvio eseguire:

```bash
python configure.py
```

Lo script ricava automaticamente il percorso assoluto della cartella del progetto e genera nella stessa cartella `config.json`, impostando `DATABASE_URL` verso `app.db`. Per mantenere compatibile la versione attuale del backend viene generato anche `.env` con lo stesso valore, evitando modifiche manuali legate al percorso del PC.

## 5. Avvio

```bash
uvicorn main:app --host 127.0.0.1 --port 8000
```

Aprire quindi [http://127.0.0.1:8000](http://127.0.0.1:8000). La documentazione Swagger è disponibile in [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

## Dataset dimostrativo

Il file `seed.sql` crea un insieme di utenti utilizzabili per verificare i diversi profili dell'applicazione. **La password di tutti gli account è `admin`.**

### Admin

- Admin Sistema — `admin@admin.it` — password: `admin`

### Nutrizionisti

- Laura Bianchi — `nutrizionista1@nutrizionista.it` — password: `admin`
- Matteo Verdi — `nutrizionista2@nutrizionista.it` — password: `admin`

### Pazienti

- Marco Rossi — `paziente1@paziente.it` — password: `admin`
- Giulia Conti — `paziente2@paziente.it` — password: `admin`
- Luca Romano — `paziente3@paziente.it` — password: `admin`
- Sara Gallo — `paziente4@paziente.it` — password: `admin`
- Elena Greco — `paziente5@paziente.it` — password: `admin`
