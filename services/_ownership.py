from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from .exceptions import ForbiddenError

async def verifica_appartenenza_paziente(session: AsyncSession,paziente_id: int,nutrizionista_id: int,*,richiedi_attivo: bool,messaggio: str = ("Il paziente non appartiene a questo nutrizionista")) -> None:
    """
    Verifica che il paziente sia assegnato al nutrizionista indicato
    Se 'richiedi_attivo' è True controlla anche che l’account del paziente sia attivo
    """
    condizioni = [
        "pp.utente_id = :paziente_id",
        "pp.nutrizionista_id = :nutrizionista_id",
        "u.ruolo = 'P'",
    ]
    # Se richiesto, la relazione è valida solo per un paziente con account attivo
    if richiedi_attivo:
        condizioni.append("u.stato = 'A'")
    result = await session.execute(
        text(
            f"""
            SELECT 1
            FROM profilo_paziente pp
            JOIN utente u ON u.id = pp.utente_id
            WHERE {' AND '.join(condizioni)}
            """
        ),
        {
            "paziente_id": paziente_id,
            "nutrizionista_id": nutrizionista_id,
        },
    )
    # Nessuna corrispondenza (il paziente no soddisfa i vincoli)
    if result.first() is None:
        raise ForbiddenError(messaggio)
