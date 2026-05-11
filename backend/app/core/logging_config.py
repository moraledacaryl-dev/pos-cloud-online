import json
import logging
from contextvars import ContextVar

_request_id: ContextVar[str] = ContextVar('request_id', default='-')


class RequestIdFilter(logging.Filter):
    def filter(self, record):
        record.request_id = _request_id.get()
        return True


def set_request_id(value: str):
    _request_id.set(value)


def configure_logging(level: str = 'INFO'):
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s %(request_id)s %(message)s'))
        handler.addFilter(RequestIdFilter())
        root.addHandler(handler)
    else:
        for handler in root.handlers:
            handler.addFilter(RequestIdFilter())
    return root


def log_json(logger: logging.Logger, level: str, event: str, **payload):
    message = json.dumps({'event': event, **payload}, ensure_ascii=False, default=str)
    getattr(logger, level.lower(), logger.info)(message)
