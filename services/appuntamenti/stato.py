from datetime import datetime, timedelta
from typing import Any, Iterable, Literal
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from schemas.appuntamento import AppuntamentoCreate, AppuntamentoResponse
from schemas.enums import AzioneAppuntamento, Ruolo, StatoAppuntamento
from .. import configurazione
from .._common import APP_TZ, iso_utc as _iso, parse_utc as _parse_dt, require as _require, utc_now as _now
from .._transaction import write_transaction
from ..exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from .comune import STATO_LABEL,TESTO_DISDETTA_DEFAULT,_config_ore,_get_app,_get_tipo_utilizzabile,_normalizza_no_tx,_normalizzazioni_pendenti,_verifica_appartenenza_paziente
from .context import AppointmentActor
from .slot import _valida_slot

def _clean_motivo(value: str | None) -> str:
    """Verifica la presenza del motivo e lo ripulisce"""
    motivo = (value or "").strip()
    if not motivo:
        raise ValidationError("Il motivo è obbligatorio")
    return motivo

async def _normalizza_actor_no_tx(session: AsyncSession, actor: AppointmentActor) -> int:
    """Normalizza le proposte scadute associate all'actor senza aprire una nuova transazione"""
    return await _normalizza_no_tx(session,nutrizionista_id=actor.nutrizionista_id,paziente_id=actor.paziente_id if actor.is_paziente else None)

async def _normalizza_actor_se_necessario(session: AsyncSession, actor: AppointmentActor) -> None:
    """
    Normalizza le proposte scadute associate all'actor solo quando necessario.
    Esegue prima un controllo senza acquisire il lock di scrittura di SQLite e apre una transazione 'BEGIN IMMEDIATE' soltanto se esistono normalizzazioni pendenti
    """
    nutrizionista_id = actor.nutrizionista_id
    paziente_id = actor.paziente_id if actor.is_paziente else None
    if not await _normalizzazioni_pendenti(session, nutrizionista_id=nutrizionista_id, paziente_id=paziente_id):
        return
    async with write_transaction(session, immediate=True):
        await _normalizza_no_tx(session, nutrizionista_id=nutrizionista_id, paziente_id=paziente_id)


async def crea_appuntamento(session: AsyncSession, *, dati: AppuntamentoCreate, actor: AppointmentActor) -> int:
    """
    Crea una nuova proposta di appuntamento per il paziente associato al nutrizionista loggato.
    Verifica tipo, appartenenza, anticipo minimo e disponibilità dello slot prima di salvare la proposta con lo stato iniziale previsto
    """
    paziente_id = actor.require_paziente_id()
    async with write_transaction(session, immediate=True):
        await _normalizza_actor_no_tx(session, actor)
        tipo = await _get_tipo_utilizzabile(session,tipo_id=dati.tipo_appuntamento_id,actor=actor)

        await _verifica_appartenenza_paziente(session, paziente_id, actor.nutrizionista_id)
        # Lo stato iniziale dipende da chi propone l’appuntamento e dall’eventuale conferma automatica
        stato_iniziale = (
            "C"
            if tipo.conferma_automatica
            else ("P" if actor.is_paziente else "N")
        )
        inizio = _parse_dt(dati.data_ora_inizio)
        ore_risposta, ore_annullamento = await _config_ore(session)
        # La prenotazione deve rispettare il preavviso minimo previsto dalla configurazione
        if inizio < _now() + timedelta(hours=ore_risposta + ore_annullamento):
            raise ValidationError("L’appuntamento non è prenotabile. Selezionare uno slot successivo al termine minimo previsto")
        fine = inizio + timedelta(minutes=tipo.durata)
        await _valida_slot(session,nutrizionista_id=actor.nutrizionista_id,inizio=inizio,fine=fine)
        row = (
            await session.execute(
                text(
                    "INSERT INTO appuntamento ("
                    "nutrizionista_id,paziente_id,data_ora_inizio,data_ora_fine,"
                    "stato,motivo,nome,descrizione,prezzo_cent,durata,"
                    "note_nutrizionista,data_evento) VALUES ("
                    ":nid,:pid,:inizio,:fine,:stato,NULL,:nome,:descrizione,"
                    ":prezzo,:durata,:note,:evento) RETURNING id"
                ),
                {
                    "nid": actor.nutrizionista_id,
                    "pid": paziente_id,
                    "inizio": _iso(inizio),
                    "fine": _iso(fine),
                    "stato": stato_iniziale,
                    "nome": tipo.nome,
                    "descrizione": tipo.descrizione,
                    "prezzo": tipo.prezzo_base_cent,
                    "durata": tipo.durata,
                    "note": dati.note_nutrizionista,
                    "evento": _iso(_now()) if stato_iniziale == "C" else None,
                },
            )
        ).mappings().first()
        row = _require(row, "Riga attesa non trovata dopo la query")
        return int(row["id"])

async def _applica_transizione(session: AsyncSession, *, app_id: int, stato_atteso: str, nuovo_stato: str, motivo: str | None, data_evento: datetime | None) -> int:
    """Applica una transizione di stato all'appuntamento solo se si trova nello stato atteso"""
    updated = (
        await session.execute(
            text(
                "UPDATE appuntamento SET stato=:stato, motivo=:motivo, "
                "data_evento=:evento WHERE id=:id AND stato=:atteso RETURNING id"
            ),
            {
                "stato": nuovo_stato,
                "motivo": motivo,
                "evento": _iso(data_evento) if data_evento else None,
                "id": app_id,
                "atteso": stato_atteso,
            },
        )
    ).mappings().first()
    # Se lo stato atteso non coincide, la transizione non deve essere applicata
    if updated is None:
        raise ConflictError("Lo stato dell’appuntamento è cambiato durante l’operazione")
    return int(updated["id"])

async def _verifica_titolare(session: AsyncSession, *, row: dict[str, Any], actor: AppointmentActor) -> None:
    """Verifica che l'actor possa accedere all'appuntamento richiesto"""
    # Il paziente può agire solo sui propri appuntamenti ed il nutrizionista solo sui pazienti in carico
    if actor.is_paziente:
        if int(row["paziente_id"]) != actor.utente_id:
            raise NotFoundError("Appuntamento", int(row["id"]))
        return
    try:
        await _verifica_appartenenza_paziente(session, int(row["paziente_id"]), actor.nutrizionista_id)
    except ForbiddenError:
        raise NotFoundError("Appuntamento", int(row["id"])) from None

async def accetta_appuntamento(session: AsyncSession, *, app_id: int, actor: AppointmentActor) -> int:
    """Accetta una proposta e la porta nello stato confermato"""
    async with write_transaction(session, immediate=True):
        await _normalizza_actor_no_tx(session, actor)
        row = await _get_app(session, app_id)
        await _verifica_titolare(session, row=row, actor=actor)
        # Ogni ruolo può accettare soltanto le proposte che sono in attesa della sua risposta
        expected = "N" if actor.is_paziente else "P"
        expired_state = "U" if actor.is_paziente else "D"
        if row["stato"] == expired_state:
            raise ConflictError("La proposta è scaduta e non può più essere accettata")
        if row["stato"] != expected:
            raise ValidationError("L’accettazione non è consentita")
        updated_id = await _applica_transizione(session,app_id=app_id,stato_atteso=expected,nuovo_stato="C",motivo=None,data_evento=_now())
        return updated_id

async def rifiuta_appuntamento(session: AsyncSession, *, app_id: int, actor: AppointmentActor, motivo: str) -> int:
    """Rifiuta una proposta e la porta nello stato rifiutato, utilizzando una motivazione obbligatoria"""
    clean = _clean_motivo(motivo)
    async with write_transaction(session, immediate=True):
        await _normalizza_actor_no_tx(session, actor)
        row = await _get_app(session, app_id)
        await _verifica_titolare(session, row=row, actor=actor)
        # Il ruolo determina sia lo stato atteso sia lo stato finale del rifiuto
        expected = "N" if actor.is_paziente else "P"
        target = "Q" if actor.is_paziente else "R"
        expired_state = "U" if actor.is_paziente else "D"
        if row["stato"] == expired_state:
            raise ConflictError("La proposta è scaduta ed è stata rifiutata automaticamente")
        if row["stato"] != expected:
            raise ValidationError("Il rifiuto non è consentito")
        updated_id = await _applica_transizione(session,app_id=app_id,stato_atteso=expected,nuovo_stato=target,motivo=clean,data_evento=_now())
        return updated_id

async def annulla_appuntamento(session: AsyncSession, *, app_id: int, actor: AppointmentActor, motivo: str, ore_minime_preavviso: int | None = None) -> int:
    """Annulla una proposta propria o un appuntamento confermato"""
    clean = _clean_motivo(motivo)
    async with write_transaction(session, immediate=True):
        await _normalizza_actor_no_tx(session, actor)
        row = await _get_app(session, app_id)
        await _verifica_titolare(session, row=row, actor=actor)
        # Un pagamento già registrato rende definitivo l’appuntamento rispetto all’annullamento 
        if row.get("pagato_at"):
            raise ConflictError("Un appuntamento già pagato non può essere annullato")
        state = str(row["stato"])
        now = _now()
        expired_state = "D" if actor.is_paziente else "U"
        if state == expired_state:
            raise ConflictError("La proposta era già scaduta ed è stata rifiutata automaticamente")

        # Per il paziente viene distinta una proposta propria da un appuntamento già confermato
        if actor.is_paziente:
            if state == "P":
                target = "A"
            elif state == "C":
                fine = _parse_dt(row["data_ora_fine"])
                if now >= fine:
                    raise ValidationError("Non è possibile annullare un appuntamento finito")
                _, configured = await _config_ore(session)
                soglia = (
                    configured
                    if ore_minime_preavviso is None
                    else ore_minime_preavviso
                )

                # Sotto la soglia di preavviso l’annullamento viene registrato come disdetta tardiva
                target = (
                    "A"
                    if _parse_dt(row["data_ora_inizio"]) - now
                    >= timedelta(hours=soglia)
                    else "T"
                )
            else:
                raise ValidationError("Il paziente può annullare solo una propria proposta o un appuntamento confermato")
        else:
            if state not in {"N", "C"}:
                raise ValidationError("Il nutrizionista può annullare solo una propria proposta o un appuntamento confermato")
            if state == "C" and now >= _parse_dt(row["data_ora_fine"]):
                raise ValidationError("L'appuntamento finitonon annullato può essere solo effettuato o marcato come mancata presenza")
            target = "X"
        updated_id = await _applica_transizione(session,app_id=app_id,stato_atteso=state,nuovo_stato=target,motivo=clean,data_evento=now)
        return updated_id

async def _chiudi_confermato(session: AsyncSession, *, app_id: int, actor: AppointmentActor, stato: Literal["E", "M"], motivo: str | None) -> int:
    """Chiude un appuntamento confermato come effettuato o mancata presenza"""
    # La chiusura dell’appuntamento è un’azione riservata al nutrizionista
    if actor.ruolo is not Ruolo.nutrizionista:
        raise ForbiddenError("Operazione riservata al nutrizionista")
    async with write_transaction(session, immediate=True):
        await _normalizza_actor_no_tx(session, actor)
        row = await _get_app(session, app_id)
        if int(row["nutrizionista_id"]) != actor.nutrizionista_id:
            raise NotFoundError("Appuntamento", app_id)
        if row["stato"] != "C":
            raise ValidationError(
                "L’operazione è consentita solo su un appuntamento confermato"
            )
        if stato == "M" and row.get("pagato_at"):
            raise ConflictError(
                "Un appuntamento già pagato non può diventare una mancata presenza"
            )
        fine = _parse_dt(row["data_ora_fine"])
        if _now() < fine - timedelta(minutes=15):
            raise ValidationError("L’operazione è consentita solo negli ultimi 15 minuti dell’appuntamento o dopo la sua conclusione")
        updated_id = await _applica_transizione(session,app_id=app_id,stato_atteso="C",nuovo_stato=stato,motivo=motivo,data_evento=_now())
        return updated_id

async def marca_appuntamento_eseguito(session: AsyncSession, *, app_id: int, actor: AppointmentActor) -> int:
    """Marca come effettuato un appuntamento confermato e già concluso"""
    return await _chiudi_confermato(session, app_id=app_id, actor=actor, stato="E", motivo=None)

async def marca_mancata_presenza(session: AsyncSession, *, app_id: int, actor: AppointmentActor, motivo: str) -> int:
    """Marca come mancata presenza un appuntamento confermato e già concluso"""
    return await _chiudi_confermato(session,app_id=app_id,actor=actor,stato="M",motivo=_clean_motivo(motivo))

async def _joined_rows(session: AsyncSession, *, actor: AppointmentActor, app_id: int | None = None, stati: Iterable[str] | None = None, data_da: datetime | None = None, data_a: datetime | None = None, limit: int = 500, skip: int = 0) -> list[dict[str, Any]]:
    """Recupera gli appuntamenti visibili insieme ai dati anagrafici"""
    sql = (
        "SELECT a.*, "
        "trim(up.nome || ' ' || up.cognome) AS paziente_nome, "
        "trim(un.nome || ' ' || un.cognome) AS nutrizionista_nome, "
        "CASE WHEN a.pagato_at IS NULL THEN 0 ELSE 1 END AS pagato "
        "FROM appuntamento a "
        "JOIN profilo_paziente pp ON pp.utente_id=a.paziente_id "
        "JOIN utente up ON up.id=a.paziente_id "
        "JOIN utente un ON un.id=a.nutrizionista_id "
        "WHERE pp.nutrizionista_id=:nid"
    )
    params: dict[str, Any] = {
        "nid": actor.nutrizionista_id,
        "limit": limit,
        "skip": skip,
    }
    if actor.paziente_id is not None:
        sql += " AND a.paziente_id=:pid"
        params["pid"] = actor.paziente_id
    if app_id is not None:
        sql += " AND a.id=:aid"
        params["aid"] = app_id
    if stati is not None:
        state_list = list(stati)
        if not state_list:
            return []
        placeholders = []
        for index, state in enumerate(state_list):
            key = f"s{index}"
            placeholders.append(f":{key}")
            params[key] = state
        sql += " AND a.stato IN (" + ",".join(placeholders) + ")"
    if data_da is not None:
        sql += " AND a.data_ora_inizio>=:data_da"
        params["data_da"] = _iso(data_da)
    if data_a is not None:
        sql += " AND a.data_ora_inizio<:data_a"
        params["data_a"] = _iso(data_a)
    sql += " ORDER BY a.data_ora_inizio DESC LIMIT :limit OFFSET :skip"
    rows = (await session.execute(text(sql), params)).mappings().all()
    return [dict(row) for row in rows]

async def _response_context(session: AsyncSession) -> tuple[int, int, str]:
    """Recupera i parametri di configurazione necessari alla costruzione delle risposte (AppuntamentoResponse)"""
    config = await configurazione.leggi_configurazione(session)
    testo = config.testo_avviso_disdetta_tardiva
    return (
        config.ore_massime_risposta_appuntamento,
        config.ore_minime_annullamento_appuntamento,
        testo.strip() if testo and testo.strip() else TESTO_DISDETTA_DEFAULT,
    )

def _to_response(row: dict[str, Any], *, actor: AppointmentActor, ore_risposta: int, ore_annullamento: int, testo_disdetta: str) -> AppuntamentoResponse:
    """Converte un record del database nella risposta esposta API"""
    now = _now()
    state = str(row["stato"])
    start = _parse_dt(row["data_ora_inizio"])
    end = _parse_dt(row["data_ora_fine"])
    scadenza = (
        _parse_dt(row["proposta_at"]) + timedelta(hours=ore_risposta)
        if state in {"P", "N"}
        else None
    )
    proposta_valida = scadenza is None or now < scadenza
    puo_rispondere = (
        (actor.is_paziente and state == "N")
        or (not actor.is_paziente and state == "P")
    ) and proposta_valida
    pagato = bool(row.get("pagato"))
    
    # Vengono verificati i permessi e le azioni disponibili in base a ruolo, stato, scadenza e presenza del pagamento
    if actor.is_paziente:
        puo_annullare = not pagato and ((state == "P" and proposta_valida) or (state == "C" and now < end))
    else:
        puo_annullare = not pagato and ((state == "N" and proposta_valida) or (state == "C" and now < end))
    azioni: list[AzioneAppuntamento] = []
    if puo_rispondere:
        azioni.extend([AzioneAppuntamento.accetta, AzioneAppuntamento.rifiuta])
    if puo_annullare:
        azioni.append(AzioneAppuntamento.annulla)
    if not actor.is_paziente and state == "C" and now >= end:
        azioni.append(AzioneAppuntamento.eseguito)
        if not pagato:
            azioni.append(AzioneAppuntamento.mancata_presenza)

    # L’avviso di disdetta tardiva riguarda solo il paziente entro la finestra configurata
    tardivo = (
        not pagato
        and actor.is_paziente
        and state == "C"
        and now < end
        and start - now < timedelta(hours=ore_annullamento)
    )
    return AppuntamentoResponse(
        id=row["id"],
        nutrizionista_id=row["nutrizionista_id"],
        paziente_id=row["paziente_id"],
        paziente_nome=row.get("paziente_nome"),
        nutrizionista_nome=row.get("nutrizionista_nome"),
        data_ora_inizio=start.astimezone(APP_TZ),
        data_ora_fine=end.astimezone(APP_TZ),
        stato=StatoAppuntamento(state),
        stato_label=STATO_LABEL[state],
        motivo=row.get("motivo"),
        data_evento=(
            _parse_dt(row["data_evento"]).astimezone(APP_TZ)
            if row.get("data_evento")
            else None
        ),
        note_nutrizionista=(
            row.get("note_nutrizionista") if not actor.is_paziente else None
        ),
        tipo={
            "nome": row["nome"],
            "descrizione": row.get("descrizione"),
            "durata_minuti": row["durata"],
            "prezzo_cent": row["prezzo_cent"],
        },
        scadenza_risposta=scadenza.astimezone(APP_TZ) if scadenza else None,
        azioni_consentite=azioni,
        pagato=pagato,
        annullamento_tardivo=tardivo,
        testo_avviso_annullamento=testo_disdetta if tardivo else None,
    )


def _responses(rows: list[dict[str, Any]], actor: AppointmentActor, context: tuple[int, int, str]) -> list[AppuntamentoResponse]:
    """Converte una lista di righe del database nelle relative risposte API (lista di AppuntamentoResponse)"""
    return [
        _to_response(row,actor=actor,ore_risposta=context[0],ore_annullamento=context[1],testo_disdetta=context[2])
        for row in rows
    ]

async def leggi_appuntamento_dto(session: AsyncSession, *, app_id: int, actor: AppointmentActor) -> AppuntamentoResponse:
    """Recupera un singolo appuntamento visibile e lo converte nella risposta API"""
    async with write_transaction(session, immediate=True):
        await _normalizza_actor_no_tx(session, actor)
        rows = await _joined_rows(session, actor=actor, app_id=app_id, limit=1)
        if not rows:
            raise NotFoundError("Appuntamento", app_id)
        context = await _response_context(session)
        return _to_response(rows[0],actor=actor,ore_risposta=context[0],ore_annullamento=context[1],testo_disdetta=context[2])

async def lista_appuntamenti_dto(session: AsyncSession, *, actor: AppointmentActor, stato: StatoAppuntamento | None = None, data_da: datetime | None = None, data_a: datetime | None = None, skip: int = 0, limit: int = 500) -> tuple[list[AppuntamentoResponse], bool]:
    """Recupera la lista paginata degli appuntamenti"""
    await _normalizza_actor_se_necessario(session, actor)
    rows = await _joined_rows(session,actor=actor,stati=[stato.value] if stato else None,data_da=data_da,data_a=data_a,skip=skip,limit=limit + 1)
    # La riga aggiuntiva serve a determinare se esiste una pagina successiva
    has_more = len(rows) > limit
    context = await _response_context(session)
    return _responses(rows[:limit], actor, context), has_more

async def pannello_paziente(session: AsyncSession, *, actor: AppointmentActor, verifica_appartenenza: bool = False) -> dict[str, list[AppuntamentoResponse]]:
    """
    Costruisce il pannello appuntamenti relativo al paziente.
    Recupera gli appuntamenti accessibili, aggiorna eventuali proposte scadute e li suddivide in base a stato, ruolo e data
    """
    paziente_id = actor.require_paziente_id()
    if verifica_appartenenza:
        await _verifica_appartenenza_paziente(session, paziente_id, actor.nutrizionista_id)
    await _normalizza_actor_se_necessario(session, actor)
    rows = await _joined_rows(session, actor=actor)
    context = await _response_context(session)
    items = _responses(rows, actor, context)
    now = _now().astimezone(APP_TZ)
    
    # Lo stesso insieme di appuntamenti viene suddiviso nelle sezioni mostrate dal pannello
    stato_in_attesa = "N" if actor.is_paziente else "P"
    stati_richiesta = {"P", "N", "R", "Q", "D", "U", "A", "X"}
    return {
        "prossimi_appuntamenti": sorted(
            (
                item
                for item in items
                if item.stato.value == "C" and item.data_ora_fine > now
            ),
            key=lambda item: item.data_ora_inizio,
        ),
        "richieste_da_confermare": sorted(
            (item for item in items if item.stato.value == stato_in_attesa),
            key=lambda item: item.data_ora_inizio,
        ),
        "storico_richieste": sorted(
            (
                item
                for item in items
                if item.stato.value in stati_richiesta - {stato_in_attesa}
            ),
            key=lambda item: item.data_evento or item.data_ora_inizio,
            reverse=True,
        ),
        "storico_appuntamenti_effettuati": sorted(
            (item for item in items if item.stato.value == "E"),
            key=lambda item: item.data_evento or item.data_ora_fine,
            reverse=True,
        ),
        "appuntamenti_da_chiudere": sorted(
            (
                item
                for item in items
                if not actor.is_paziente
                and item.stato.value == "C"
                and item.data_ora_fine <= now
            ),
            key=lambda item: item.data_ora_fine,
        ),
        "storico_assenze_disdette": sorted(
            (
                item
                for item in items
                if not actor.is_paziente and item.stato.value in {"M", "T"}
            ),
            key=lambda item: item.data_evento or item.data_ora_fine,
            reverse=True,
        ),
    }