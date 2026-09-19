-- Convenzioni generali:
-- - Le date senza orario sono salvate come TEXT nel formato ISO-8601 YYYY-MM-DD
-- - I timestamp sono salvati come TEXT in formato ISO-8601 con indicazione del fuso orario
-- - I booleani SQLite sono INTEGER vincolati ai valori 0 e 1

PRAGMA foreign_keys = ON; -- necessario per cancellazioni in cascata

PRAGMA synchronous = NORMAL; -- documentazione SQLite descrive synchronous=NORMAL come ottimo compromesso tra prestazioni e sicurezza se journal_mode = WAL
PRAGMA journal_mode = WAL; 

PRAGMA cache_size = -65536;
PRAGMA encoding = 'UTF-8'; -- necessario per la creazione
PRAGMA busy_timeout = 5000; -- evita il crash immediato se il database è bloccato da altre operazioni

-- UTENTI
CREATE TABLE IF NOT EXISTS utente (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL CHECK(length(nome) <= 20),
    cognome TEXT NOT NULL CHECK(length(cognome) <= 20),
    email TEXT UNIQUE NOT NULL COLLATE NOCASE CHECK(length(email) <= 100), -- username login
    telefono TEXT CHECK(length(telefono) <= 15),
    ruolo TEXT NOT NULL CHECK(ruolo IN ('A','N','P')), -- A = admin, N = nutrizionista, P = paziente
    pwd TEXT NOT NULL, 
    stato TEXT NOT NULL DEFAULT 'A' CHECK(stato IN ('A','D')), -- A = Attivo, D = Disattivo
    last_login_at TEXT -- Timestamp ISO-8601 UTC
);

CREATE TABLE IF NOT EXISTS sessione_autenticazione (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    utente_id INTEGER NOT NULL REFERENCES utente(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TEXT NOT NULL, -- scadenza per inattività, rinnovabile
    absolute_expires_at TEXT NOT NULL -- scadenza 'assoluta', mai superabile né modificabile
);

CREATE INDEX IF NOT EXISTS idx_sessione_autenticazione_utente
    ON sessione_autenticazione(utente_id);

-- Token usato per impostare la passwor
CREATE TABLE IF NOT EXISTS token_password (
    utente_id INTEGER PRIMARY KEY REFERENCES utente(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TEXT NOT NULL

);

CREATE TABLE IF NOT EXISTS profilo_nutrizionista (
    utente_id INTEGER PRIMARY KEY REFERENCES utente(id) ON DELETE CASCADE

);

CREATE TABLE IF NOT EXISTS profilo_paziente (
    utente_id INTEGER PRIMARY KEY REFERENCES utente(id) ON DELETE CASCADE,
    nutrizionista_id INTEGER NOT NULL REFERENCES profilo_nutrizionista(utente_id) ON DELETE RESTRICT, -- associazione permanente
    codice_fiscale TEXT UNIQUE CHECK(length(codice_fiscale) <= 16), -- tenuto separato dall'ID per un discorso di prestazioni
    data_nascita TEXT NOT NULL, -- DATE ISO-8601
    sesso TEXT NOT NULL CHECK(sesso IN ('M','F')),
    peso_obiettivo_kg REAL CHECK(peso_obiettivo_kg > 0),
    note_nutrizionista TEXT -- note visibili esclusivamente dal nutrizionista 
);

CREATE TRIGGER IF NOT EXISTS trg_profilo_paziente_nutrizionista_immutabile
BEFORE UPDATE OF nutrizionista_id ON profilo_paziente
WHEN NEW.nutrizionista_id <> OLD.nutrizionista_id
BEGIN
    SELECT RAISE(ABORT, 'Il nutrizionista del paziente non può essere modificato');
END;


-- APPUNTAMENTI
-- stato:
-- P = In attesa di conferma del nutrizionista
-- N = In attesa di conferma del paziente
-- C = Confermato
-- R = Rifiutato dal nutrizionista
-- Q = Rifiutato dal paziente
-- D = Rifiuto automatico - mancata risposta del nutrizionista
-- U = Rifiuto automatico - mancata risposta del paziente
-- A = Annullato dal paziente
-- X = Annullato dal nutrizionista
-- T = Disdetta tardiva
-- M = Mancata presenza
-- E = Effettuato

CREATE TABLE IF NOT EXISTS tipo_appuntamento (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL CHECK(length(trim(nome)) BETWEEN 1 AND 75),
    descrizione TEXT,
    prezzo_base_cent INTEGER NOT NULL DEFAULT 0 CHECK(prezzo_base_cent >= 0), -- importo in centesimi
    nutrizionista_id INTEGER NOT NULL REFERENCES profilo_nutrizionista(utente_id) ON DELETE CASCADE,
    durata INTEGER NOT NULL CHECK(durata >= 15 AND durata % 15 = 0),
    prenotabile_paziente INTEGER NOT NULL DEFAULT 1 CHECK(prenotabile_paziente IN (0,1)), -- 1 = il paziente può creare appuntamenti di questa tipologia
    conferma_automatica INTEGER NOT NULL DEFAULT 0 CHECK(conferma_automatica IN (0,1)) -- 1 = la prenotazione nasce già confermata, senza accettazione manuale

);

CREATE TABLE IF NOT EXISTS appuntamento (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nutrizionista_id INTEGER NOT NULL REFERENCES profilo_nutrizionista(utente_id) ON DELETE CASCADE,
    paziente_id INTEGER NOT NULL REFERENCES profilo_paziente(utente_id) ON DELETE CASCADE,
    data_ora_inizio TEXT NOT NULL,
    data_ora_fine TEXT NOT NULL CHECK(data_ora_fine > data_ora_inizio),
    stato TEXT NOT NULL CHECK(stato IN ('P','N','C','R','Q','D','U','A','X','T','M','E')),
    motivo TEXT, -- obbligatorio per rifiuti, annullamenti, disdette tardive e mancate presenze
    nome TEXT NOT NULL,
    descrizione TEXT,
    prezzo_cent INTEGER NOT NULL CHECK(prezzo_cent >= 0), -- importo in centesimi
    sconto_cent INTEGER NOT NULL DEFAULT 0 CHECK(sconto_cent >= 0 AND sconto_cent <= prezzo_cent),
    pagato_at TEXT,
    durata INTEGER NOT NULL CHECK(durata >= 15 AND durata % 15 = 0),
    note_nutrizionista TEXT, -- note private del nutrizionista
    data_evento TEXT, -- timestamp dell'ultimo evento rilevante di stato (conferma, rifiuto, annullamento, effettuazione, ecc.)
    proposta_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')), -- timestamp dell'inizio dell'attuale proposta (P/N), usato per calcolare la scadenza di risposta
    CHECK(stato NOT IN ('R','Q','D','U','A','X','T','M') OR (motivo IS NOT NULL AND length(trim(motivo)) > 0))
);

CREATE INDEX IF NOT EXISTS idx_appuntamento_nutrizionista_stato_inizio
    ON appuntamento(nutrizionista_id, stato, data_ora_inizio);
CREATE INDEX IF NOT EXISTS idx_appuntamento_paziente_stato_inizio
    ON appuntamento(paziente_id, stato, data_ora_inizio);
CREATE UNIQUE INDEX IF NOT EXISTS uq_tipo_appuntamento_nutrizionista_nome
    ON tipo_appuntamento(nutrizionista_id, nome COLLATE NOCASE);

-- DISPONIBILITÀ E INDISPONIBILITÀ
-- Le disponibilità sono ricorrenti per giorno della settimana
-- le indisponibilità invece intervalli temporali senza regolarità
CREATE TABLE IF NOT EXISTS disponibilita (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nutrizionista_id INTEGER NOT NULL REFERENCES profilo_nutrizionista(utente_id) ON DELETE CASCADE,
    giorno_settimana INTEGER NOT NULL CHECK(giorno_settimana BETWEEN 0 AND 6),
    ora_inizio TEXT NOT NULL CHECK(substr(ora_inizio, 4, 2) IN ('00','15','30','45')),
    ora_fine TEXT NOT NULL CHECK(ora_fine > ora_inizio) CHECK(substr(ora_fine, 4, 2) IN ('00','15','30','45'))

);

CREATE INDEX IF NOT EXISTS idx_disponibilita_nutrizionista_giorno
    ON disponibilita(nutrizionista_id, giorno_settimana, ora_inizio, ora_fine);

CREATE TABLE IF NOT EXISTS indisponibilita (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nutrizionista_id INTEGER NOT NULL REFERENCES profilo_nutrizionista(utente_id) ON DELETE CASCADE,
    data_ora_inizio TEXT NOT NULL,
    data_ora_fine TEXT NOT NULL CHECK(data_ora_fine > data_ora_inizio),
    motivo TEXT NOT NULL CHECK(length(trim(motivo)) > 0)

);

CREATE INDEX IF NOT EXISTS idx_indisponibilita_nutrizionista_intervallo
    ON indisponibilita(nutrizionista_id, data_ora_inizio, data_ora_fine);


-- DIETE E TEMPLATE

CREATE TABLE IF NOT EXISTS dieta (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nutrizionista_id INTEGER NOT NULL REFERENCES profilo_nutrizionista(utente_id) ON DELETE CASCADE,
    paziente_id INTEGER REFERENCES profilo_paziente(utente_id) ON DELETE CASCADE,
    is_template INTEGER NOT NULL DEFAULT 0 CHECK(is_template IN (0,1)),
    nome TEXT NOT NULL CHECK(length(nome) <= 200),
    tipo TEXT NOT NULL CHECK(tipo IN ('G','S')), -- G = giornaliero, S = settimanale
    stato TEXT CHECK(stato IN ('A','R')), -- NULL per i template; A = attiva, R = archiviata
    data_inizio_validita TEXT,
    data_fine_validita TEXT,
    archiviata_at TEXT,
    note TEXT, -- descrizione del template oppure note visibili al paziente
    note_nutrizionista TEXT, -- visibile esclusivamente dal nutrizionista
    considerazioni_finali TEXT, -- modificabile solo sulla dieta archiviata
    CHECK(
        (is_template = 1
            AND paziente_id IS NULL
            AND stato IS NULL
            AND data_inizio_validita IS NULL
            AND data_fine_validita IS NULL
            AND archiviata_at IS NULL
            AND note_nutrizionista IS NULL
            AND considerazioni_finali IS NULL)
        OR
        (is_template = 0
            AND paziente_id IS NOT NULL
            AND data_inizio_validita IS NOT NULL
            AND (
                (stato = 'A' AND data_fine_validita IS NULL AND archiviata_at IS NULL)
                OR
                (stato = 'R' AND data_fine_validita IS NOT NULL AND archiviata_at IS NOT NULL)
            )
            AND (data_fine_validita IS NULL OR data_fine_validita >= data_inizio_validita)
            AND (considerazioni_finali IS NULL OR stato = 'R'))
    )
);

CREATE TRIGGER IF NOT EXISTS trg_dieta_nutrizionista_paziente_insert
BEFORE INSERT ON dieta
WHEN NEW.is_template = 0
  AND NOT EXISTS (
      SELECT 1 FROM profilo_paziente pp
      WHERE pp.utente_id = NEW.paziente_id
        AND pp.nutrizionista_id = NEW.nutrizionista_id
  )
BEGIN
    SELECT RAISE(ABORT, 'La dieta deve appartenere al nutrizionista permanente del paziente');
END;

CREATE TRIGGER IF NOT EXISTS trg_dieta_nutrizionista_paziente_update
BEFORE UPDATE OF nutrizionista_id, paziente_id, is_template ON dieta
WHEN NEW.is_template = 0
  AND NOT EXISTS (
      SELECT 1 FROM profilo_paziente pp
      WHERE pp.utente_id = NEW.paziente_id
        AND pp.nutrizionista_id = NEW.nutrizionista_id
  )
BEGIN
    SELECT RAISE(ABORT, 'La dieta deve appartenere al nutrizionista permanente del paziente');
END;

CREATE TABLE IF NOT EXISTS pasto (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dieta_id INTEGER NOT NULL REFERENCES dieta(id) ON DELETE CASCADE,
    ordine INTEGER NOT NULL DEFAULT 0,
    nome TEXT NOT NULL CHECK(length(nome) <= 200),
    giorno_settimana INTEGER CHECK(giorno_settimana BETWEEN 0 AND 6),
    note TEXT

);

-- Opzione completa di un pasto (es. "Opzione 1", "Opzione 2"):
CREATE TABLE IF NOT EXISTS opzione_pasto (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pasto_id INTEGER NOT NULL
        REFERENCES pasto(id) ON DELETE CASCADE,
    ordine INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS alimento (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    opzione_id INTEGER NOT NULL
        REFERENCES opzione_pasto(id) ON DELETE CASCADE,
    ordine INTEGER NOT NULL DEFAULT 0,
    descrizione TEXT NOT NULL
        CHECK(length(trim(descrizione)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_dieta_nutrizionista_template_nome
    ON dieta(nutrizionista_id, is_template, nome, id);
CREATE INDEX IF NOT EXISTS idx_dieta_paziente_stato
    ON dieta(paziente_id, stato, id) WHERE is_template = 0;
CREATE UNIQUE INDEX IF NOT EXISTS idx_dieta_unica_attiva_paziente
    ON dieta(paziente_id) WHERE is_template = 0 AND stato = 'A';
CREATE INDEX IF NOT EXISTS idx_pasto_dieta_ordine
    ON pasto(dieta_id, ordine, id);
CREATE INDEX IF NOT EXISTS idx_opzione_pasto_ordine
    ON opzione_pasto(pasto_id, ordine, id);
CREATE INDEX IF NOT EXISTS idx_alimento_opzione_ordine
    ON alimento(opzione_id, ordine, id);

-- MISURAZIONI

CREATE TABLE IF NOT EXISTS misurazione (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paziente_id INTEGER NOT NULL REFERENCES profilo_paziente(utente_id) ON DELETE CASCADE,
    data TEXT NOT NULL, -- DATE ISO-8601 'YYYY-MM-DD'
    peso_kg REAL NOT NULL CHECK(peso_kg > 0),
    altezza_cm REAL NOT NULL CHECK(altezza_cm > 0),

    plica_tricipitale_mm REAL NOT NULL CHECK(plica_tricipitale_mm > 0), -- obbligatoria: pliche Durnin-Womersley 
    plica_bicipitale_mm REAL NOT NULL CHECK(plica_bicipitale_mm > 0), -- obbligatoria: pliche Durnin-Womersley 
    plica_sottoscapolare_mm REAL NOT NULL CHECK(plica_sottoscapolare_mm > 0), -- obbligatoria: pliche Durnin-Womersley 
    plica_sovrailiaca_mm REAL NOT NULL CHECK(plica_sovrailiaca_mm > 0), -- obbligatoria: pliche Durnin-Womersley 
    plica_ombelicale_mm REAL CHECK(plica_ombelicale_mm > 0),
    plica_pettorale_mm REAL CHECK(plica_pettorale_mm > 0),
    plica_coscia_mm REAL CHECK(plica_coscia_mm > 0),

    circ_vita_cm REAL CHECK(circ_vita_cm > 0),
    circ_fianchi_cm REAL CHECK(circ_fianchi_cm > 0),
    circ_bicipite_cm REAL CHECK(circ_bicipite_cm > 0),
    circ_coscia_cm REAL CHECK(circ_coscia_cm > 0),
    circ_torace_cm REAL CHECK(circ_torace_cm > 0),
    circ_addome_cm REAL CHECK(circ_addome_cm > 0),

    massa_grassa_perc REAL, -- congelata all'inserimento
    note_nutrizionista TEXT, -- note visibili esclusivamente dal nutrizionista 
    note_paziente TEXT -- note visibili anche al paziente nella sua area
);

-- DATI MEDICI DEL PAZIENTE

CREATE TABLE IF NOT EXISTS paziente_dato_medico (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paziente_id INTEGER NOT NULL REFERENCES profilo_paziente(utente_id) ON DELETE CASCADE,
    tipo TEXT NOT NULL CHECK(tipo IN ('P','A','F','T')), -- P = Patologia, A = Allergia, F = Farmaco, T = Terapia
    descrizione TEXT NOT NULL
);

-- Indici aggiuntivi per filtri frequenti
CREATE INDEX IF NOT EXISTS idx_profilo_paziente_nutrizionista ON profilo_paziente(nutrizionista_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_misurazione_paziente_data ON misurazione(paziente_id, data);
CREATE INDEX IF NOT EXISTS idx_paziente_dato_medico_paziente ON paziente_dato_medico(paziente_id, tipo);
CREATE INDEX IF NOT EXISTS idx_appuntamento_nutrizionista_pagato ON appuntamento(nutrizionista_id, pagato_at);


-- CONFIGURAZIONE APPLICAZIONE

CREATE TABLE IF NOT EXISTS configurazione_app (
    chiave TEXT PRIMARY KEY,
    valore TEXT NOT NULL,
    descrizione TEXT

);

INSERT OR IGNORE INTO configurazione_app (chiave, valore, descrizione)
VALUES (
    'ore_massime_risposta_appuntamento',
    '24',
    'Tempo massimo, in ore, per accettare o rifiutare una proposta'
);

INSERT OR IGNORE INTO configurazione_app (chiave, valore, descrizione)
VALUES (
    'ore_minime_annullamento_appuntamento',
    '24',
    'Ore minime per non classificare una cancellazione come tardiva'
);

INSERT OR IGNORE INTO configurazione_app (chiave, valore, descrizione)
VALUES (
    'testo_avviso_disdetta_tardiva',
    'Stai annullando l’appuntamento oltre il termine previsto. La disdetta verrà registrata come tardiva e sarà visibile nello storico degli appuntamenti. Inserisci una motivazione per proseguire.',
    'Testo mostrato al paziente prima di una disdetta tardiva'
);

INSERT OR IGNORE INTO configurazione_app (chiave, valore, descrizione)
VALUES ('sessione_timeout_inattivita_ore', '1', 'Scadenza per inattività della sessione, in ore (rinnovabile)');

INSERT OR IGNORE INTO configurazione_app (chiave, valore, descrizione)
VALUES ('sessione_durata_assoluta_ore', '6', 'Scadenza assoluta della sessione, in ore (non rinnovabile)');

INSERT OR IGNORE INTO configurazione_app (chiave, valore, descrizione)
VALUES ('token_password_validita_ore', '24', 'Validità del link di impostazione password, in ore');