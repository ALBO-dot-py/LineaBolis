
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

@asynccontextmanager
async def write_transaction(session: AsyncSession,*,immediate: bool = False) -> AsyncIterator[None]:
    """
    Apre una transazione di scrittura sulla sessione data
    -Se 'immediate=False' usa 'session.begin()', che con SQLite acquisisce il lock sul database solo alla prima scrittura effettiva
    -Se 'immediate=True' esegue esplicitamente 'BEGIN IMMEDIATE', che acquisisce subito il lock di scrittura

    Se il blocco termina correttamente esegue il commit quando necessario, in caso invece di eccezione viene eseguito il rollback e propagato l'errore
    """
    if session.in_transaction():
        transaction = session.get_transaction()
        auto_started = bool(
            transaction
            and transaction.sync_transaction.origin.name == "AUTOBEGIN"
        )
        try:
            async with session.begin_nested():
                yield
        except Exception:
            if auto_started:
                await session.rollback()
            raise
        else:
            if auto_started:
                await session.commit()
        return

    if not immediate:
        async with session.begin():
            yield
        return

    try:
        await session.execute(text("BEGIN IMMEDIATE"))
        yield
    except Exception:
        if session.in_transaction():
            await session.rollback()
        raise
    else:
        await session.commit()
