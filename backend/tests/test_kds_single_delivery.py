"""KDS in-memory SSE fan-out must deliver one event per subscribed channel.

The broadcaster fixture is completely isolated: no HTTP clients, Redis,
cashier transactions, physical kitchen devices or production server traffic.
"""

import asyncio

from app.services import kds_stream


def test_station_events_reach_global_listener_once():
    async def scenario():
        broadcaster = kds_stream._Broadcaster()
        global_q = await broadcaster.subscribe('*')
        kitchen_q = await broadcaster.subscribe('kitchen')
        bar_q = await broadcaster.subscribe('bar')
        await broadcaster.publish('*', {'event': 'refresh'})
        await broadcaster.publish('kitchen', {'event': 'refresh'})
        assert global_q.qsize() == 1
        assert kitchen_q.qsize() == 1
        assert bar_q.empty()
        assert (await global_q.get())['event'] == 'refresh'
        assert (await kitchen_q.get())['event'] == 'refresh'
        await broadcaster.unsubscribe('*', global_q)
        await broadcaster.unsubscribe('kitchen', kitchen_q)
        await broadcaster.unsubscribe('bar', bar_q)
        assert await broadcaster.listener_count() == 0

    asyncio.run(scenario())


def test_multi_station_event_delivers_exactly_once_per_wildcard_and_station(monkeypatch):
    async def scenario():
        broadcaster = kds_stream._Broadcaster()
        monkeypatch.setattr(kds_stream, '_broadcaster', broadcaster)
        global_q = await broadcaster.subscribe('*')
        kitchen_q = await broadcaster.subscribe('kitchen')
        bar_q = await broadcaster.subscribe('bar')
        cafe_q = await broadcaster.subscribe('cafe')

        await kds_stream.publish_kds_event(
            'ticket_finalized', {'order_id': 42},
            stations=['kitchen', 'kitchen', 'bar', '*', '', None],
        )
        assert [global_q.qsize(), kitchen_q.qsize(), bar_q.qsize(), cafe_q.qsize()] == [1, 1, 1, 0]
        messages = [await q.get() for q in (global_q, kitchen_q, bar_q)]
        assert all(m['event'] == 'ticket_finalized' for m in messages)
        assert all(m['payload'] == {'order_id': 42} for m in messages)
        assert len({m['ts'] for m in messages}) == 1
        assert global_q.empty() and kitchen_q.empty() and bar_q.empty()

    asyncio.run(scenario())


def test_global_only_event_not_delivered_to_station_channels(monkeypatch):
    async def scenario():
        broadcaster = kds_stream._Broadcaster()
        monkeypatch.setattr(kds_stream, '_broadcaster', broadcaster)
        global_q = await broadcaster.subscribe('*')
        kitchen_q = await broadcaster.subscribe('kitchen')
        await kds_stream.publish_kds_event('global_refresh', {'ok': True})
        assert global_q.qsize() == 1
        assert kitchen_q.empty()

    asyncio.run(scenario())


def test_slow_listener_eviction_preserved_with_single_delivery():
    async def scenario():
        broadcaster = kds_stream._Broadcaster()
        stalled = await broadcaster.subscribe('kitchen')
        healthy = await broadcaster.subscribe('kitchen')
        for _ in range(100):
            stalled.put_nowait({'event': 'old'})
        await broadcaster.publish('kitchen', {'event': 'fresh'})
        assert stalled.qsize() == 100
        assert healthy.qsize() == 1
        assert (await healthy.get())['event'] == 'fresh'
        assert await broadcaster.listener_count() == 1
        await broadcaster.unsubscribe('kitchen', healthy)
        assert await broadcaster.listener_count() == 0

    asyncio.run(scenario())


def test_stream_generator_global_sse_has_exactly_one_frame(monkeypatch):
    async def scenario():
        broadcaster = kds_stream._Broadcaster()
        monkeypatch.setattr(kds_stream, '_broadcaster', broadcaster)
        stream = kds_stream.stream_kds_events('*', keepalive_seconds=1)
        try:
            hello = await anext(stream)
            assert 'event: hello' in hello
            await kds_stream.publish_kds_event('ticket_updated', {'order_id': 9}, stations=['kitchen', 'bar'])
            event_frame = await asyncio.wait_for(anext(stream), timeout=1)
            assert 'event: ticket_updated' in event_frame
            assert '"order_id":9' in event_frame
            assert broadcaster._listeners['*']
            assert next(iter(broadcaster._listeners['*'])).empty()
        finally:
            await stream.aclose()
        assert await broadcaster.listener_count() == 0

    asyncio.run(scenario())
