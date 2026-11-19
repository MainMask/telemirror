"""The live mirror: ``python -m telemirror.live`` (``telemirror@<key>.service``)."""

import asyncio
import logging
import sys
from typing import Optional

from aiohttp import web

from telemirror.mirroring import Telemirror
from telemirror.notify import BotNotifier
from telemirror.misc.log_setup import setup_stdout_logger
from telemirror.misc.session_lock import SessionBusy, lock_session
from telemirror.misc.signals import cancel_on_sigterm
from telemirror.sink import LiveSink
from telemirror.storage import open_database


async def serve_health_endpoint(host: str, port: int) -> web.AppRunner:
    """Answer 204 at ``/`` — systemd's health check (``telemirror.health``)
    polls it. Returns the runner to clean up on exit."""

    async def health(_):
        return web.Response(status=204)

    app = web.Application()
    app.add_routes([web.get("/", health)])
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, host, port).start()
    return runner


async def run_telemirror(
    db_url: Optional[str],
    api_id: str,
    api_hash: str,
    api_device_model: Optional[str],
    api_system_version: Optional[str],
    api_app_version: Optional[str],
    session_string: str,
    chat_mapping: dict,
    logger: logging.Logger,
    host: str,
    port: int,
    broadcast_channel: Optional[int] = None,
    api_lang_pack: Optional[str] = None,
    api_system_lang_code: Optional[str] = None,
    project_key: Optional[str] = None,
):
    # return_exceptions=True: with the default False, gather() propagates the
    # first exception without cancelling the other awaitable, which keeps
    # running in the background — if the DB side succeeds after the health
    # side already raised, the opened connection pool would never be
    # assigned anywhere and so never closed. Handle both outcomes ourselves
    # so whatever opened is always closed before we re-raise.
    health_result, db_result = await asyncio.gather(
        serve_health_endpoint(host=host, port=port), open_database(db_url, logger),
        return_exceptions=True,
    )
    if isinstance(db_result, BaseException):
        if isinstance(health_result, BaseException):
            logger.error(health_result, exc_info=health_result)
        else:
            await health_result.cleanup()
        raise db_result
    database = db_result
    if isinstance(health_result, BaseException):
        await database.close()
        raise health_result
    runner = health_result

    try:
        notifier = BotNotifier.from_env(project_key, "live")
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
            api_lang_pack=api_lang_pack,
            api_system_lang_code=api_system_lang_code,
            broadcast_channel=broadcast_channel,
            notifier=notifier,
            chat_names_key=project_key,
            sink=LiveSink(project_key, notifier, chat_mapping) if project_key else None,
        )
        cancel_on_sigterm()
        await telemirror.run()
    except asyncio.CancelledError:
        pass
    finally:
        await database.close()
        await runner.cleanup()


def main():
    from telemirror.config import (
        API_APP_VERSION,
        API_DEVICE_MODEL,
        API_HASH,
        API_ID,
        API_LANG_PACK,
        API_SYSTEM_LANG_CODE,
        API_SYSTEM_VERSION,
        BROADCAST_CHANNEL,
        CHAT_MAPPING,
        DB_URL,
        HOST,
        LOG_LEVEL,
        PORT,
        SESSION_FILE,
        SESSION_STRING,
        TELEMIRROR_PROJECT,
    )

    if SESSION_FILE:
        try:
            lock_session(SESSION_FILE)
        except SessionBusy as e:
            sys.exit(str(e))

    if sys.platform == "win32":
        if DB_URL is not None:
            # required by psycopg async pool on windows platform
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    else:
        import uvloop

        uvloop.install()

    asyncio.run(
        run_telemirror(
            db_url=DB_URL,
            api_id=API_ID,
            api_hash=API_HASH,
            api_device_model=API_DEVICE_MODEL,
            api_system_version=API_SYSTEM_VERSION,
            api_app_version=API_APP_VERSION,
            api_lang_pack=API_LANG_PACK,
            api_system_lang_code=API_SYSTEM_LANG_CODE,
            session_string=SESSION_STRING,
            chat_mapping=CHAT_MAPPING,
            logger=setup_stdout_logger("telemirror", LOG_LEVEL),
            host=HOST,
            port=PORT,
            broadcast_channel=BROADCAST_CHANNEL,
            project_key=TELEMIRROR_PROJECT,
        )
    )


if __name__ == "__main__":
    main()
