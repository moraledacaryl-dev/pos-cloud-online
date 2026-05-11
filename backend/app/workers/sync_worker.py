import asyncio
import logging

from app.core.settings import settings
from app.db.database import SessionLocal
from app.services.sync_service import record_sync_worker_heartbeat, run_outbox_sync

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def loop_forever():
    while True:
        try:
            with SessionLocal() as db:
                result = await run_outbox_sync(db, limit=settings.sync_worker_batch_size)
                record_sync_worker_heartbeat(db, status='ok', result=result)
                logger.info('sync worker cycle: %s', result)
        except Exception as exc:
            logger.exception('sync worker error: %s', exc)
            try:
                with SessionLocal() as db:
                    record_sync_worker_heartbeat(db, status='failed', error=str(exc))
            except Exception:
                logger.exception('failed to persist sync worker heartbeat')
        await asyncio.sleep(settings.sync_worker_poll_seconds)


if __name__ == '__main__':
    asyncio.run(loop_forever())
