import asyncio
import logging
from typing import Optional

from telemirror.mirroring import Telemirror
from telemirror.misc.log_setup import setup_stdout_logger
from telemirror.misc.signals import cancel_on_sigterm
from telemirror.storage import InMemoryDatabase, PostgresDatabase, warn_memory_db_limits


async def serve_health_endpoint(host: str, port: int) -> None:
    """
    Start http health endpoint at /.

    Some PaaS providers require a health endpoint to verify that the service has started successfully.
    """
    from aiohttp import web

    async def health(_):
        return web.Response(status=204)

    app = web.Application()
    app.add_routes([web.get("/", health)])

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()


async def run_telemirror(
    use_memory_db: bool,
    db_uri: str,
    api_id: str,
    api_hash: str,
    api_device_model: str,
    api_system_version: str,
    api_app_version: str,
    session_string: str,
    chat_mapping: dict,
    logger: logging.Logger,
    host: str,
    port: int,
    broadcast_channel: Optional[int] = None,
    tech_channel: Optional[int] = None,
):
    if use_memory_db:
        warn_memory_db_limits(logger)

    db_awaitable = (
        InMemoryDatabase() if use_memory_db else PostgresDatabase(connection_string=db_uri)
    )
    # return_exceptions=True: with the default False, gather() propagates the
    # first exception without cancelling the other awaitable, which keeps
    # running in the background — if the DB side succeeds after the health
    # side already raised, the opened connection pool would never be
    # assigned anywhere and so never closed. Handle both outcomes ourselves
    # so a successfully-opened database is always closed before we re-raise.
    health_result, db_result = await asyncio.gather(
        serve_health_endpoint(host=host, port=port), db_awaitable,
        return_exceptions=True,
    )
    if isinstance(db_result, BaseException):
        raise db_result
    database = db_result
    if isinstance(health_result, BaseException):
        await database.close()
        raise health_result

    telemirror = Telemirror(
        api_id=api_id,
        api_hash=api_hash,
        session_string=session_string,
        chat_mapping=chat_mapping,
        database=database,
        logger=logger,
        api_device_model=api_device_model,
        api_system_version=api_system_version,
        api_app_version=api_app_version,
        broadcast_channel=broadcast_channel,
        tech_channel=tech_channel,
    )
    cancel_on_sigterm()
    try:
        await telemirror.run()
    except asyncio.CancelledError:
        pass
    finally:
        await database.close()


def main():
    import asyncio
    import sys

    from config import (
        API_APP_VERSION,
        API_DEVICE_MODEL,
        API_HASH,
        API_ID,
        API_SYSTEM_VERSION,
        BROADCAST_CHANNEL,
        TECH_CHANNEL,
        CHAT_MAPPING,
        DB_URL,
        HOST,
        LOG_LEVEL,
        PORT,
        SESSION_STRING,
        USE_MEMORY_DB,
    )

    if sys.platform == "win32":
        if USE_MEMORY_DB is False:
            # required by psycopg async pool on windows platform
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    else:
        import uvloop

        uvloop.install()

    asyncio.run(
        run_telemirror(
            use_memory_db=USE_MEMORY_DB,
            db_uri=DB_URL,
            api_id=API_ID,
            api_hash=API_HASH,
            api_device_model=API_DEVICE_MODEL,
            api_system_version=API_SYSTEM_VERSION,
            api_app_version=API_APP_VERSION,
            session_string=SESSION_STRING,
            chat_mapping=CHAT_MAPPING,
            logger=setup_stdout_logger("telemirror", LOG_LEVEL),
            host=HOST,
            port=PORT,
            broadcast_channel=BROADCAST_CHANNEL,
            tech_channel=TECH_CHANNEL,
        )
    )


if __name__ == "__main__":
    main()
