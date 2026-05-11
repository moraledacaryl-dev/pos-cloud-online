from __future__ import annotations

import asyncio
import json
import time
from collections import defaultdict
from typing import AsyncIterator


class _Broadcaster:
    def __init__(self):
        self._listeners: dict[str, set[asyncio.Queue]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def subscribe(self, channel: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        async with self._lock:
            self._listeners[channel].add(queue)
        return queue

    async def unsubscribe(self, channel: str, queue: asyncio.Queue):
        async with self._lock:
            listeners = self._listeners.get(channel)
            if listeners and queue in listeners:
                listeners.remove(queue)
            if listeners and not listeners:
                self._listeners.pop(channel, None)

    async def publish(self, channel: str, payload: dict):
        async with self._lock:
            targets = list(self._listeners.get(channel, set())) + list(self._listeners.get('*', set()))
        dropped = []
        for queue in targets:
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                dropped.append(queue)
        if dropped:
            async with self._lock:
                for channel_name, listeners in list(self._listeners.items()):
                    for queue in dropped:
                        listeners.discard(queue)
                    if not listeners:
                        self._listeners.pop(channel_name, None)


_broadcaster = _Broadcaster()


def sse_frame(data: dict, event: str = 'message') -> str:
    return f"event: {event}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"


async def publish_kds_event(event: str, payload: dict | None = None, *, stations: list[str] | None = None):
    message = {
        'event': event,
        'payload': payload or {},
        'ts': round(time.time(), 3),
    }
    await _broadcaster.publish('*', message)
    for station in {s for s in (stations or []) if s}:
        await _broadcaster.publish(station, message)


async def stream_kds_events(channel: str | None = None, keepalive_seconds: int = 20) -> AsyncIterator[str]:
    queue = await _broadcaster.subscribe(channel or '*')
    try:
        yield sse_frame({'ok': True, 'channel': channel or '*'}, event='hello')
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=keepalive_seconds)
                yield sse_frame(item.get('payload') or {}, event=item.get('event') or 'message')
            except asyncio.TimeoutError:
                yield ': keepalive\n\n'
    finally:
        await _broadcaster.unsubscribe(channel or '*', queue)
