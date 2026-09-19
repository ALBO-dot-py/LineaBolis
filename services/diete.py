from datetime import date, datetime
from typing import Any, Iterable
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from schemas.dieta import DietaCreateRequest, DietaStrutturaRequest, DietaUpdateRequest, PastoPayload
from schemas.enums import StatoDieta, TipoDieta
from ._common import APP_TZ, require
from ._ownership import verifica_appartenenza_paziente
from ._transaction import write_transaction
from .exceptions import NotFoundError, ValidationError

_PLICHE = (
    ("tricipitale", "plica_tricipitale_mm"), ("bicipitale", "plica_bicipitale_mm"),
    ("sottoscapolare", "plica_sottoscapolare_mm"), ("sovrailiaca", "plica_sovrailiaca_mm"),
    ("ombelicale", "plica_ombelicale_mm"), ("pettorale", "plica_pettorale_mm"),
    ("coscia", "plica_coscia_mm"),
)

async def _owned_record(session: AsyncSession, record_id: int, nutrizionista_id: int, *, template: bool) -> dict[str, Any]:
    """
    Viene caricata una dieta o un template verificandone la proprietà del nutrizionista
    -'template' distingue i template dalle diete assegnate a un paziente
    """
    row = (await session.execute(text(
        "SELECT d.*, trim(u.nome || ' ' || u.cognome) AS nutrizionista_nome "
        "FROM dieta d JOIN utente u ON u.id=d.nutrizionista_id "
        "WHERE d.id=:id AND d.is_template=:template"
    ), {"id": record_id, "template": int(template)})).mappings().first()
    nome = "Template dieta" if template else "Dieta"

    # Template e diete di altri nutrizionisti sono trattati come non disponibili
    if row is None or int(row["nutrizionista_id"]) != nutrizionista_id:
        raise NotFoundError(nome, record_id)
    record = dict(row)

    # Per la dieta assegnata verifichiamo anche che il paziente sia a lui associato
    if not template:
        await verifica_appartenenza_paziente(session, int(record["paziente_id"]), nutrizionista_id,richiedi_attivo=False, messaggio="il paziente non appartiene al nutrizionista",)
    return record

async def _save_structure(session: AsyncSession, dieta_id: int, pasti: Iterable[PastoPayload]) -> None:
    """Viene sostituita la struttura dei pasti della dieta mantenendo l’ordine di pasti, opzioni e alimenti"""
    # La struttura viene sostituita integralmente, così non restano elementi della versione precedente
    await session.execute(text("DELETE FROM pasto WHERE dieta_id=:id"), {"id": dieta_id})
    for ordine_pasto, pasto in enumerate(pasti):
        row = (await session.execute(text(
            "INSERT INTO pasto (dieta_id,ordine,nome,giorno_settimana,note) "
            "VALUES (:dieta,:ordine,:nome,:giorno,:note) RETURNING id"
        ), {"dieta": dieta_id, "ordine": ordine_pasto, "nome": pasto.nome,
            "giorno": pasto.giorno_settimana, "note": pasto.note})).first()
        pasto_id = int(require(row, "Pasto inserito non trovato")[0])
        for ordine_opzione, opzione in enumerate(pasto.opzioni):
            row = (await session.execute(text(
                "INSERT INTO opzione_pasto (pasto_id,ordine) VALUES (:pasto,:ordine) RETURNING id"
            ), {"pasto": pasto_id, "ordine": ordine_opzione})).first()
            opzione_id = int(require(row, "Opzione inserita non trovata")[0])
            await session.execute(text(
                "INSERT INTO alimento (opzione_id,ordine,descrizione) "
                "VALUES (:opzione,:ordine,:descrizione)"
            ), [{"opzione": opzione_id, "ordine": i, "descrizione": alimento.descrizione}
                for i, alimento in enumerate(opzione.alimenti)])

async def _load_full(session: AsyncSession, record: dict[str, Any], *, public: bool = False) -> dict[str, Any]:
    """
    Viene ricostruita la dieta completa caricando pasti, opzioni e alimenti collegati
    -'public=True' rimuove i campi riservati al nutrizionista prima della risposta
    """
    result = dict(record)
    pasti = [dict(row) for row in (await session.execute(text(
        "SELECT id,ordine,nome,giorno_settimana,note FROM pasto "
        "WHERE dieta_id=:id ORDER BY ordine,id"
    ), {"id": result["id"]})).mappings().all()]
    by_meal = {int(p["id"]): p for p in pasti}
    for pasto in pasti:
        pasto["opzioni"] = []
    # Colleghiamo prima le opzioni ai rispettivi pasti
    if by_meal:
        by_option: dict[int, dict[str, Any]] = {}
        rows = (await session.execute(text(
            "SELECT o.id,o.pasto_id,o.ordine FROM opzione_pasto o "
            "JOIN pasto p ON p.id=o.pasto_id WHERE p.dieta_id=:id "
            "ORDER BY p.ordine,p.id,o.ordine,o.id"
        ), {"id": result["id"]})).mappings().all()
        for row in rows:
            option = dict(row); meal_id = int(option.pop("pasto_id")); option["alimenti"] = []
            by_option[int(option["id"])] = option; by_meal[meal_id]["opzioni"].append(option)
        # Completiamo ogni opzione con i relativi alimenti
        if by_option:
            rows = (await session.execute(text(
                "SELECT a.id,a.opzione_id,a.ordine,a.descrizione FROM alimento a "
                "JOIN opzione_pasto o ON o.id=a.opzione_id JOIN pasto p ON p.id=o.pasto_id "
                "WHERE p.dieta_id=:id ORDER BY p.ordine,p.id,o.ordine,o.id,a.ordine,a.id"
            ), {"id": result["id"]})).mappings().all()
            for row in rows:
                food = dict(row); option_id = int(food.pop("opzione_id"))
                by_option[option_id]["alimenti"].append(food)
    # La vista pubblica non espone le info riservate al nutrizionista
    if public:
        for field in ("note_nutrizionista", "considerazioni_finali", "archiviata_at"):
            result.pop(field, None)
    result["pasti"] = pasti
    return result

async def _save_header(session: AsyncSession, *, nutrizionista_id: int, dati: DietaStrutturaRequest | DietaUpdateRequest,template: bool, record_id: int | None = None, paziente_id: int | None = None,data_inizio: date | None = None,) -> dict[str, Any]:
    """
    Crea o aggiorna i dati principali di una dieta o di un template
    -'record_id=None' indica una nuova risorsa
    -'template' determina i campi e lo stato applicabili
    """
    # Senza ''record_id'' creiamo una nuova intestazione; altrimenti aggiorniamo quella esistente.
    if record_id is None:
        row = (await session.execute(text(
            "INSERT INTO dieta (nutrizionista_id,paziente_id,is_template,nome,tipo,stato,"
            "data_inizio_validita,data_fine_validita,archiviata_at,note,note_nutrizionista,considerazioni_finali) "
            "VALUES (:nid,:pid,:template,:nome,:tipo,:stato,:inizio,NULL,NULL,:note,:private,NULL) RETURNING *"
        ), {"nid": nutrizionista_id, "pid": paziente_id, "template": int(template),
            "nome": dati.nome, "tipo": dati.tipo.value,
            "stato": None if template else StatoDieta.attiva.value,
            "inizio": data_inizio.isoformat() if data_inizio else None,
            "note": dati.note, "private": getattr(dati, "note_nutrizionista", None)})).mappings().first()
    else:
        private_sql = "" if template else ",note_nutrizionista=:private"
        row = (await session.execute(text(
            f"UPDATE dieta SET nome=:nome,tipo=:tipo,note=:note{private_sql} "
            "WHERE id=:id AND is_template=:template RETURNING *"
        ), {"id": record_id, "template": int(template), "nome": dati.nome,
            "tipo": dati.tipo.value, "note": dati.note,
            "private": getattr(dati, "note_nutrizionista", None)})).mappings().first()
    return dict(require(row, "Dieta salvata non trovata"))

def _progress(dieta: dict[str, Any], rows: list[dict[str, Any]], goal: float | None) -> dict[str, Any]:
    """Vnegono calcolati i progressi registrati durante il periodo di validità della dieta, incluso l’avvicinamento al peso obiettivo"""
    start = date.fromisoformat(str(dieta["data_inizio_validita"])[:10])
    end = date.fromisoformat(str(dieta["data_fine_validita"])[:10]) if dieta.get("data_fine_validita") else None
    # Considerate solo le misurazioni registrate durante la validità della dieta
    values = [r for r in rows if (day := date.fromisoformat(str(r["data"])[:10])) >= start and (end is None or day <= end)]
    result: dict[str, Any] = {"dieta_id": int(dieta["id"]), "dati_sufficienti": len(values) >= 2, "pliche_delta": {}}
    # Necessarie almeno due misurazioni per calcolare una variazione
    if len(values) < 2:
        return result
    first, last = values[0], values[-1]
    delta = lambda field: None if first.get(field) is None or last.get(field) is None else round(float(last[field]) - float(first[field]), 2)
    result.update({
        "prima_misurazione_id": first["id"], "ultima_misurazione_id": last["id"],
        "data_prima_misurazione": first["data"], "data_ultima_misurazione": last["data"],
        "kg_delta": delta("peso_kg"), "massa_grassa_delta": delta("massa_grassa_perc"),
        "pliche_delta": {name: value for name, field in _PLICHE if (value := delta(field)) is not None},
    })
    if goal is not None:
        result["obiettivo_delta_kg"] = round(
            abs(float(first["peso_kg"]) - float(goal)) - abs(float(last["peso_kg"]) - float(goal)), 2
        )
    return result

async def lista_template(session: AsyncSession, *, nutrizionista_id: int, tipo: TipoDieta | None = None,skip: int = 0, limit: int = 50) -> list[dict[str, Any]]:
    """Vengono restituiti i template del nutrizionista (filtrabili per tipologia e paginazione)"""
    sql = "SELECT id,nome,tipo,note FROM dieta WHERE nutrizionista_id=:nid AND is_template=1"
    params: dict[str, Any] = {"nid": nutrizionista_id, "skip": skip, "limit": limit}
    if tipo is not None:
        sql += " AND tipo=:tipo"; params["tipo"] = tipo.value
    sql += " ORDER BY nome,id LIMIT :limit OFFSET :skip"
    return [dict(row) for row in (await session.execute(text(sql), params)).mappings().all()]

async def salva_template(session: AsyncSession, *, dati: DietaStrutturaRequest, nutrizionista_id: int,template_id: int | None = None) -> dict[str, Any]:
    """Viene creato o aggiornato un template di una dieta e ne viene sostituita l’intera struttura dei pasti"""
    async with write_transaction(session):
        # In aggiornamento viene verificata l'appartenzna al nutrizionista
        if template_id is not None:
            await _owned_record(session, template_id, nutrizionista_id, template=True)
        record = await _save_header(session, nutrizionista_id=nutrizionista_id, dati=dati,template=True, record_id=template_id)
        await _save_structure(session, int(record["id"]), dati.pasti)
        return await _load_full(session, record)

async def leggi_template(session: AsyncSession, *, template_id: int, nutrizionista_id: int) -> dict[str, Any]:
    """Viene restituito un template dopo averne verificato la proprietà"""
    return await _load_full(session, await _owned_record(session, template_id, nutrizionista_id, template=True))

async def elimina_template(session: AsyncSession, *, template_id: int, nutrizionista_id: int) -> None:
    """Viene eliminato un template di dieta appartenente al nutrizionista"""
    async with write_transaction(session):
        await _owned_record(session, template_id, nutrizionista_id, template=True)
        await session.execute(text("DELETE FROM dieta WHERE id=:id AND is_template=1"), {"id": template_id})

async def salva_dieta_attiva(session: AsyncSession, *, dati: DietaCreateRequest | DietaUpdateRequest,nutrizionista_id: int, dieta_id: int | None = None,) -> dict[str, Any]:
    """
    Viene creata una nuova dieta attiva oppure aggiornata quella indicata da 'dieta_id'
    (In creazione vengono archiviate automatichemente la dieta attiva precedente)
    """
    # Se è presente un ID viene aggiornata la dieta attiva indicata
    if dieta_id is not None:
        async with write_transaction(session):
            record = await _owned_record(session, dieta_id, nutrizionista_id, template=False)
            if record["stato"] != StatoDieta.attiva.value:
                raise ValidationError("possibile modificare solamente la dieta attiva")
            record = await _save_header(session, nutrizionista_id=nutrizionista_id, dati=dati,
                                        template=False, record_id=dieta_id)
            await _save_structure(session, dieta_id, dati.pasti)
            return await _load_full(session, record)

    # In creazione il paziente deve essere presente nella richiesta
    if not isinstance(dati, DietaCreateRequest):
        raise ValidationError("paziente obbligatorio per creare una dieta")
    now = datetime.now(APP_TZ); transition = now.date()
    async with write_transaction(session, immediate=True):
        # Prima di salvare la nuova dieta viene archiviata l’eventuale dieta attiva precedente
        await verifica_appartenenza_paziente(
            session, dati.paziente_id, nutrizionista_id, richiedi_attivo=False,
            messaggio="Paziente non appartenente al nutrizionista",
        )
        await session.execute(text(
            "UPDATE dieta SET stato=:archived,data_fine_validita=:day,archiviata_at=:now "
            "WHERE paziente_id=:pid AND nutrizionista_id=:nid AND is_template=0 AND stato=:active"
        ), {"archived": StatoDieta.archiviata.value, "day": transition.isoformat(), "now": now.isoformat(),
            "pid": dati.paziente_id, "nid": nutrizionista_id, "active": StatoDieta.attiva.value})
        record = await _save_header(session, nutrizionista_id=nutrizionista_id, dati=dati,
                                    template=False, paziente_id=dati.paziente_id, data_inizio=transition)
        await _save_structure(session, int(record["id"]), dati.pasti)
        return await _load_full(session, record)

async def leggi_dieta(session: AsyncSession, *, dieta_id: int, nutrizionista_id: int) -> dict[str, Any]:
    """Viene restituita una dieta completa"""
    return await _load_full(session, await _owned_record(session, dieta_id, nutrizionista_id, template=False))

async def get_dieta_attiva(session: AsyncSession, *, paziente_id: int,nutrizionista_id: int | None = None) -> dict[str, Any]:
    """
    Restituisce la dieta attiva del paziente.
    -se 'nutrizionista_id' assente esclude i campi riservati al nutrizionista
    """
    params: dict[str, Any] = {"pid": paziente_id, "active": StatoDieta.attiva.value}
    owner = ""
    # Se la lettura avviene come nutrizionista, viene ferificata l’appartenenza del paziente
    if nutrizionista_id is not None:
        await verifica_appartenenza_paziente(session, paziente_id, nutrizionista_id, richiedi_attivo=False)
        params["nid"] = nutrizionista_id; owner = " AND d.nutrizionista_id=:nid"
    row = (await session.execute(text(
        "SELECT d.*,trim(u.nome || ' ' || u.cognome) AS nutrizionista_nome "
        "FROM dieta d JOIN utente u ON u.id=d.nutrizionista_id "
        "WHERE d.paziente_id=:pid AND d.is_template=0 AND d.stato=:active" + owner +
        " ORDER BY d.id DESC LIMIT 1"
    ), params)).mappings().first()
    if row is None:
        raise NotFoundError("dieta attiva")
    return await _load_full(session, dict(row), public=nutrizionista_id is None)

async def get_diete_nutrizionista(session: AsyncSession, *, paziente_id: int,nutrizionista_id: int) -> dict[str, Any]:
    """Viene restituita la dieta attiva e lo storico delle diete del paziente, arricchite con i relativi progressi"""
    await verifica_appartenenza_paziente(session, paziente_id, nutrizionista_id, richiedi_attivo=False)
    diets = [dict(row) for row in (await session.execute(text(
        "SELECT d.*,trim(u.nome || ' ' || u.cognome) AS nutrizionista_nome "
        "FROM dieta d JOIN utente u ON u.id=d.nutrizionista_id "
        "WHERE d.paziente_id=:pid AND d.nutrizionista_id=:nid AND d.is_template=0 "
        "ORDER BY CASE d.stato WHEN 'A' THEN 0 ELSE 1 END,d.data_fine_validita DESC,d.id DESC"
    ), {"pid": paziente_id, "nid": nutrizionista_id})).mappings().all()]
    # Senza diete viene restituita una struttura vuota
    if not diets:
        return {"attiva": None, "archiviate": []}
    measurements = [dict(row) for row in (await session.execute(text(
        "SELECT * FROM misurazione WHERE paziente_id=:pid ORDER BY data,id"
    ), {"pid": paziente_id})).mappings().all()]
    goal = (await session.execute(text(
        "SELECT peso_obiettivo_kg FROM profilo_paziente WHERE utente_id=:pid AND nutrizionista_id=:nid"
    ), {"pid": paziente_id, "nid": nutrizionista_id})).scalar_one_or_none()
    # Ogni dieta viene arricchita con i progressi relativi al proprio periodo di validità
    for dieta in diets:
        dieta["progressi"] = _progress(dieta, measurements, goal)
    return {
        "attiva": next((d for d in diets if d["stato"] == StatoDieta.attiva.value), None),
        "archiviate": [d for d in diets if d["stato"] == StatoDieta.archiviata.value],
    }

async def archivia_dieta(session: AsyncSession, *, dieta_id: int, nutrizionista_id: int,considerazioni_finali: str | None = None) -> dict[str, Any]:
    """Viene archiviata la dieta attiva popolando la data di fine e le eventuali considerazioni finali"""
    now = datetime.now(APP_TZ)
    async with write_transaction(session, immediate=True):
    # Solo la dieta attiva può essere chiusa e spostata nello storico
        record = await _owned_record(session, dieta_id, nutrizionista_id, template=False)
        if record["stato"] != StatoDieta.attiva.value:
            raise ValidationError("dieta è già archiviata")
        row = (await session.execute(text(
            "UPDATE dieta SET stato=:archived,data_fine_validita=:day,archiviata_at=:now,"
            "considerazioni_finali=:notes WHERE id=:id AND nutrizionista_id=:nid "
            "AND is_template=0 AND stato=:active RETURNING *"
        ), {"archived": StatoDieta.archiviata.value, "day": now.date().isoformat(), "now": now.isoformat(),
            "notes": considerazioni_finali, "id": dieta_id, "nid": nutrizionista_id,
            "active": StatoDieta.attiva.value})).mappings().first()
        return await _load_full(session, dict(require(row, "dieta non trovata")))

async def aggiorna_considerazioni_finali(session: AsyncSession, *, dieta_id: int, nutrizionista_id: int,considerazioni_finali: str | None,) -> dict[str, Any]:
    """Vnegono aggiornate le considerazioni finali su una dieta già archiviata"""
    async with write_transaction(session):
        record = await _owned_record(session, dieta_id, nutrizionista_id, template=False)
        if record["stato"] != StatoDieta.archiviata.value:
            raise ValidationError("considerazioni finali sono modificabili solo se la dieta è archiviata")
        row = (await session.execute(text(
            "UPDATE dieta SET considerazioni_finali=:notes WHERE id=:id AND nutrizionista_id=:nid "
            "AND is_template=0 AND stato=:archived RETURNING *"
        ), {"notes": considerazioni_finali, "id": dieta_id, "nid": nutrizionista_id,
            "archived": StatoDieta.archiviata.value})).mappings().first()
        return await _load_full(session, dict(require(row, "dieta non trovata")))
