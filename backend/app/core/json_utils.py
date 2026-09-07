from __future__ import annotations

import json
from typing import Any

from fastapi.encoders import jsonable_encoder


def json_dumps(value: Any, **kwargs: Any) -> str:
    """Serialize API/domain values consistently, including Decimal and datetime."""
    return json.dumps(jsonable_encoder(value), **kwargs)
