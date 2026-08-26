#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import os
import sys

import httpx


BASE_URL = os.getenv('KDS_LOAD_BASE_URL', 'http://127.0.0.1:8100').rstrip('/')
USERNAME = os.getenv('KDS_LOAD_USERNAME', 'ci-owner')
PASSWORD = os.getenv('KDS_LOAD_PASSWORD', 'CiOwnerPassword-2026!')
BEARER = os.getenv('KDS_LOAD_BEARER', '').strip()
STREAMS = int(os.getenv('KDS_LOAD_STREAMS', '20'))


async def main() -> int:
    timeout = httpx.Timeout(connect=10.0, read=None, write=10.0, pool=10.0)
    headers = {'Authorization': f'Bearer {BEARER}'} if BEARER else {}
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=timeout, follow_redirects=False, headers=headers) as controller:
        mutation_headers = {}
        if not BEARER:
            login = await controller.post('/api/auth/login', json={'username': USERNAME, 'password': PASSWORD})
            if login.status_code != 200:
                raise RuntimeError(f'login failed: {login.status_code} {login.text[:300]}')
            csrf = controller.cookies.get('pos_csrf')
            if not csrf:
                raise RuntimeError('browser login did not set pos_csrf')
            mutation_headers['X-CSRF-Token'] = csrf

        stream_handles: list[tuple[httpx.AsyncClient, object, httpx.Response, object]] = []
        try:
            for index in range(STREAMS):
                ticket_response = await controller.post(
                    '/api/kitchen/stream-ticket',
                    json={'station': 'kitchen', 'device_id': f'ci-load-{index}'},
                    headers=mutation_headers,
                )
                if ticket_response.status_code != 200:
                    raise RuntimeError(f'stream ticket {index} failed: {ticket_response.status_code} {ticket_response.text[:300]}')
                ticket = ticket_response.json()['ticket']

                # Give every SSE connection its own HTTP client and retain the
                # response + iterator for the entire load window.  Retaining only
                # the context manager lets httpx release earlier responses when
                # later streams are opened, which falsely collapses the active
                # stream count to one.
                stream_client = httpx.AsyncClient(base_url=BASE_URL, timeout=timeout, follow_redirects=False)
                context = stream_client.stream(
                    'GET',
                    '/api/kitchen/stream',
                    params={'ticket': ticket, 'station': 'kitchen'},
                )
                response = await context.__aenter__()
                if response.status_code != 200:
                    body = await response.aread()
                    await context.__aexit__(None, None, None)
                    await stream_client.aclose()
                    raise RuntimeError(f'stream {index} failed: {response.status_code} {body[:300]!r}')
                lines = response.aiter_lines()
                first = await anext(lines)
                if first != 'event: hello':
                    await context.__aexit__(None, None, None)
                    await stream_client.aclose()
                    raise RuntimeError(f'stream {index} did not emit hello frame: {first!r}')
                stream_handles.append((stream_client, context, response, lines))

            metrics = await controller.get('/api/kitchen/stream-metrics')
            metrics.raise_for_status()
            active = int(metrics.json().get('active_streams') or 0)
            if active < STREAMS:
                raise RuntimeError(f'only {active}/{STREAMS} KDS streams registered active')

            for round_no in range(5):
                results = await asyncio.gather(
                    controller.get('/api/auth/me'),
                    controller.get('/api/kitchen/tickets'),
                    controller.get('/api/orders/'),
                )
                statuses = [response.status_code for response in results]
                if statuses != [200, 200, 200]:
                    raise RuntimeError(f'normal requests failed under KDS load round {round_no}: {statuses}')

            print(f'PASS: {STREAMS} simultaneous KDS streams did not starve auth/kitchen/order requests.')
        finally:
            for stream_client, context, _response, _lines in reversed(stream_handles):
                try:
                    await context.__aexit__(None, None, None)
                finally:
                    await stream_client.aclose()

        for _ in range(30):
            metrics = await controller.get('/api/kitchen/stream-metrics')
            metrics.raise_for_status()
            if int(metrics.json().get('active_streams') or 0) == 0:
                print('PASS: KDS active stream metric returned to zero after disconnect cleanup.')
                return 0
            await asyncio.sleep(0.1)
        raise RuntimeError(f"KDS streams did not clean up: {metrics.json()}")


if __name__ == '__main__':
    try:
        raise SystemExit(asyncio.run(main()))
    except Exception as exc:
        print(f'KDS LOAD REGRESSION FAILED: {exc}', file=sys.stderr)
        raise
