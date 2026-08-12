import asyncio
import logging

from app.core.settings import settings
from app.db.database import SessionLocal
from app.services import sync_service
from app.services.accounting_review_defaults import install_accounting_review_transport
from app.services.inventory_integration import run_inventory_outbox_sync
from app.services.sync_service import record_sync_worker_heartbeat, run_outbox_sync, sync_catalog_from_accounting, sync_in_house_bookings_from_accounting

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
install_accounting_review_transport(sync_service)


async def loop_forever():
    while True:
        try:
            with SessionLocal() as db:
                try:
                    booking_result = await sync_in_house_bookings_from_accounting(db, force=False)
                except Exception as exc:
                    booking_result = {'ok': False, 'error': str(exc)}
                    logger.warning('room charge booking sync failed: %s', exc)
                try:
                    catalog_result = await sync_catalog_from_accounting(db, force=False)
                except Exception as exc:
                    catalog_result = {'ok': False, 'error': str(exc)}
                    logger.warning('catalog sync failed: %s', exc)
                inventory_result = await run_inventory_outbox_sync(db, limit=settings.sync_worker_batch_size)
                result = await run_outbox_sync(db, limit=settings.sync_worker_batch_size)
                result['inventory'] = inventory_result
                result['room_charge_bookings'] = booking_result
                result['catalog'] = catalog_result
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
