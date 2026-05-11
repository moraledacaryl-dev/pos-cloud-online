import logging
import os


def configure_logging():
    level = os.getenv('LOG_LEVEL', 'INFO').upper()
    logging.basicConfig(
        level=level,
        format='%(asctime)s %(levelname)s %(name)s %(message)s',
        force=True,
    )
