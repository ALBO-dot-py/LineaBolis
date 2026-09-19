import math
from datetime import date
from typing import Any
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from ._common import require
from ._repo import get_by_id
from ._ownership import verifica_appartenenza_paziente as _verifica_ownership
from ._transaction import write_transaction
from schemas.enums import Sesso
from schemas.misurazione import MisurazioneCreateRequest
from .exceptions import ForbiddenError, NotFoundError, ValidationError


_READ_TABLES = {"misurazione", "profilo_paziente"}

## Funzioni private
async def _get_profilo_paziente(session: AsyncSession,paziente_id: int,) -> dict[str, Any]:
    """Legge e restituisce i dati legati al paziente"""
    row = await get_by_id(session,table="profilo_paziente",row_id=paziente_id,whitelist=_READ_TABLES,id_field="utente_id",)
    if row is None:
        raise NotFoundError("ProfiloPaziente", paziente_id)
    return row

async def _verifica_accesso(session: AsyncSession,*,paziente_id: int,nutrizionista_id: int | None,paziente_id_richiedente: int | None,) -> None:
    """
    Verifica che la misurazione sia accessibile dal nutrizionista assegnato o dal paziente stesso
    - se 'nutrizionista_id' presente, si attiva il controllo di appartenenza altrimenti viene verificato 'paziente_id_richiedente'
    """
    if nutrizionista_id is not None:
        # non richiede che account paziente sia attivo (richiedi_attivo=false)
        await _verifica_ownership(session, paziente_id, nutrizionista_id, richiedi_attivo=False)
    elif paziente_id_richiedente != paziente_id:
        raise ForbiddenError("Accesso negato")

def _as_date(value: date | str) -> date:
    """Normalizza date"""
    return value if isinstance(value, date) else date.fromisoformat(value)

def _calcola_eta(data_nascita: date | str, data_riferimento: date | str) -> int:
    """Calcola e ritorna il numero di anni alla data di misurazione"""
    nascita = _as_date(data_nascita)
    riferimento = _as_date(data_riferimento)
    if riferimento < nascita:
        raise ValidationError("data misurazione precede la nascita")
    # tolgo 1 se il compleanno dell'anno corrente non è ancora passato
    return (
        riferimento.year
        - nascita.year
        - ((riferimento.month, riferimento.day) < (nascita.month, nascita.day))
    )

def _calcola_bmi(peso_kg: float, altezza_cm: float) -> float:
    """Calcolo BMI"""
    return round(peso_kg / ((altezza_cm / 100) ** 2), 1)

def _somma_quattro_pliche(row: dict[str, Any]) -> float:
    """Somma pliche tricipitale, bicipitale, sottoscapolare, sovrailiaca per calcolo massa grassa"""
    return sum(float(row[campo]) for campo in ("plica_tricipitale_mm","plica_bicipitale_mm","plica_sottoscapolare_mm","plica_sovrailiaca_mm",))

def _calcola_massa_grassa(somma_pliche_mm: float, eta: int, sesso: str) -> float:
    """Stima massa grassa in percentuale con Durnin & Womersley"""
    if somma_pliche_mm <= 0:
        raise ValidationError("la somma pliche deve essere positiva")

    log_s = math.log10(somma_pliche_mm)

    # costanti C e M per fascia d'età
    if sesso == Sesso.maschio.value:
        fasce = (
            (17, 1.1533, 0.0643),
            (20, 1.1620, 0.0630),
            (30, 1.1631, 0.0632),
            (40, 1.1422, 0.0544),
            (50, 1.1620, 0.0700),
            (10_000, 1.1715, 0.0779), # >50 anni
        )
    else:
        fasce = (
            (17, 1.1369, 0.0598),
            (20, 1.1549, 0.0678),
            (30, 1.1599, 0.0717),
            (40, 1.1423, 0.0632),
            (50, 1.1333, 0.0612),
            (10_000, 1.1339, 0.0645), # >50 anni
        )

    # selezioniamo le costanti della prima fascia il cui limite supera l'età
    c, m = next((c, m) for limite, c, m in fasce if eta < limite)
    densita = c - m * log_s
    # equazione di Siri per la conversione densità in percentuale di grasso
    return round((4.95 / densita - 4.50) * 100, 2)

def _arricchisci_con_calcoli(row: dict[str, Any],data_nascita: date | str,sesso: str,*,per_paziente: bool = False,) -> dict[str, Any]:
    """
    Aggiunge i calcoli -> bmi, somma_pliche_mm, massa_grassa_perc
    se per_paziente=True, rimuove note_nutrizionista dalla risposta
    """
    output = dict(row)
    output["bmi"] = _calcola_bmi(float(row["peso_kg"]), float(row["altezza_cm"]))
    somma = _somma_quattro_pliche(row)
    output["somma_pliche_mm"] = round(somma, 2)
    congelata = row.get("massa_grassa_perc")
    if congelata is None:
        eta = _calcola_eta(data_nascita, row["data"])
        congelata = _calcola_massa_grassa(somma, eta, sesso)
    output["massa_grassa_perc"] = float(congelata)
    if per_paziente:
        # paziente non deve vedere le note interne del nutrizionista
        output.pop("note_nutrizionista", None)
    return output


## Funzioni pubbliche

async def crea_misurazione(session: AsyncSession,*,paziente_id: int,dati: MisurazioneCreateRequest,nutrizionista_id: int,) -> dict[str, Any]:
    """Registra una nuova misurazione al paziente"""
    valori = {"paziente_id": paziente_id, **dati.to_sqlite_dict(exclude_unset=False)}

    async with write_transaction(session, immediate=True):
        # non richiede account paziente attivo (richiedi_attivo=False)
        await _verifica_ownership(session,paziente_id,nutrizionista_id,richiedi_attivo=False,messaggio="paziente non di proprietà del nutrizionista",)
        profilo = await _get_profilo_paziente(session, paziente_id)
        eta = _calcola_eta(profilo["data_nascita"], dati.data)
        valori["massa_grassa_perc"] = _calcola_massa_grassa(_somma_quattro_pliche(valori), eta, profilo["sesso"])
        # Per ogni data viene mantenuta una sola misurazione (se esiste già, viene aggiornata)
        esistente = await session.scalar(
            text(
                "SELECT id FROM misurazione "
                "WHERE paziente_id = :paziente_id AND data = :data "
                "ORDER BY id DESC LIMIT 1"
            ),
            {"paziente_id": paziente_id, "data": valori["data"]},
        )
        colonne = [campo for campo in valori if campo != "paziente_id"]
        if esistente is None:
            insert_colonne = list(valori)
            query = (
                "INSERT INTO misurazione ("
                + ", ".join(insert_colonne)
                + ") VALUES ("
                + ", ".join(f":{campo}" for campo in insert_colonne)
                + ") RETURNING *"
            )
        else:
            valori["id"] = int(esistente)
            query = (
                "UPDATE misurazione SET "
                + ", ".join(f"{campo} = :{campo}" for campo in colonne)
                + " WHERE id = :id RETURNING *"
            )
        row = (await session.execute(text(query), valori)).mappings().first()
        row = require(row, "Errore durante il salvataggio della misurazione")
        return _arricchisci_con_calcoli(dict(row),profilo["data_nascita"],profilo["sesso"],)

async def lista_misurazioni(session: AsyncSession,*,paziente_id: int,nutrizionista_id: int | None = None,paziente_id_richiedente: int | None = None,skip: int = 0,limit: int = 50,order: str = "desc",) -> list[dict[str, Any]]:
    """Restituisce elenco paginato delle misurazioni del paziente"""
    per_paziente = paziente_id_richiedente is not None
    await _verifica_accesso(session,paziente_id=paziente_id,nutrizionista_id=nutrizionista_id,paziente_id_richiedente=paziente_id_richiedente,)
    ordine = "DESC" if order.lower() == "desc" else "ASC"
    rows = (
        await session.execute(
            text(
                f"SELECT * FROM misurazione WHERE paziente_id = :pid "
                f"ORDER BY data {ordine}, id {ordine} LIMIT :limit OFFSET :skip"
            ),
            {"pid": paziente_id, "limit": limit, "skip": skip},
        )
    ).mappings().all()
    profilo = await _get_profilo_paziente(session, paziente_id)
    return [
        _arricchisci_con_calcoli(dict(row),profilo["data_nascita"],profilo["sesso"],per_paziente=per_paziente,)
        for row in rows
    ]

async def leggi_progressi(session: AsyncSession,*,paziente_id: int,nutrizionista_id: int | None = None,paziente_id_richiedente: int | None = None,) -> dict[str, Any]:
    """Restituisce riepilogo, avanzamento e serie storica del paziente"""
    await _verifica_accesso(session,paziente_id=paziente_id,nutrizionista_id=nutrizionista_id,paziente_id_richiedente=paziente_id_richiedente,)
    profilo = await _get_profilo_paziente(session, paziente_id)
    peso_obiettivo_kg = (
        float(profilo["peso_obiettivo_kg"])
        if profilo.get("peso_obiettivo_kg") is not None
        else None
    )
    rows = (
        await session.execute(
            text(
                "SELECT * FROM misurazione WHERE paziente_id = :pid "
                "ORDER BY data ASC, id ASC"
            ),
            {"pid": paziente_id},
        )
    ).mappings().all()

    # Senza misurazioni non è possibile calcolare un avanzamento o una serie storica
    if not rows:
        return {
            "partenza": None,
            "attuale": None,
            "peso_obiettivo_kg": peso_obiettivo_kg,
            "avanzamento": None,
            "serie": [],
        }
    misurazioni = [
        _arricchisci_con_calcoli(dict(row), profilo["data_nascita"], profilo["sesso"])
        for row in rows
    ]

    def sintesi(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "data": row["data"],
            "peso_kg": float(row["peso_kg"]),
            "massa_grassa_perc": row["massa_grassa_perc"],
            "bmi": row["bmi"],
        }

    def serie(metrica: str, unita: str, campo: str) -> dict[str, Any]:
        return {
            "metrica": metrica,
            "unita": unita,
            "punti": [
                {"data": row["data"], "valore": float(row[campo])}
                for row in misurazioni[-10:]
                if row.get(campo) is not None
            ],
        }
    # Il riepilogo confronta la prima misurazione disponibile con quella più recente
    partenza = sintesi(misurazioni[0])
    attuale = sintesi(misurazioni[-1])
    peso_perso_kg = round(partenza["peso_kg"] - attuale["peso_kg"], 2)
    massa_grassa_persa = round(partenza["massa_grassa_perc"] - attuale["massa_grassa_perc"], 2)
    percentuale = None
     # Se è presente un obiettivo, si calcola quanta parte del percorso iniziale è stata coperta
    if peso_obiettivo_kg is not None:
        distanza_totale = peso_obiettivo_kg - partenza["peso_kg"]
        if distanza_totale == 0:
            percentuale = 100.0
        else:
            percorso = attuale["peso_kg"] - partenza["peso_kg"]
            percentuale = percorso / distanza_totale * 100
            percentuale = round(max(0.0, min(100.0, percentuale)), 1)
    return {
        "partenza": partenza,
        "attuale": attuale,
        "peso_obiettivo_kg": peso_obiettivo_kg,
        "avanzamento": {
            "percentuale": percentuale,
            "peso_perso_kg": peso_perso_kg,
            "massa_grassa_perc_persa": massa_grassa_persa,
            "numero_misurazioni": len(misurazioni),
        },
        "serie": [
            serie("peso", "kg", "peso_kg"),
            serie("massa_grassa", "%", "massa_grassa_perc"),
            serie("plica_tricipitale", "mm", "plica_tricipitale_mm"),
            serie("plica_bicipitale", "mm", "plica_bicipitale_mm"),
            serie("plica_sottoscapolare", "mm", "plica_sottoscapolare_mm"),
            serie("plica_sovrailiaca", "mm", "plica_sovrailiaca_mm"),
            serie("plica_ombelicale", "mm", "plica_ombelicale_mm"),
            serie("plica_pettorale", "mm", "plica_pettorale_mm"),
            serie("plica_coscia", "mm", "plica_coscia_mm"),
        ],
    }