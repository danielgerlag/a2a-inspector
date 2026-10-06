import asyncio

import httpx
import pytest
import respx

from websockets.asyncio.server import serve

from backend import app


def test_custom_declared_interface_is_retained_without_binding_assumptions():
    declarations = app._declared_inspector_websocket_interfaces(
        {
            'supportedInterfaces': [
                {
                    'url': 'https://agent.example/a2a',
                    'protocolBinding': 'JSONRPC',
                },
                {
                    'url': 'wss://agent.example/events',
                    'protocolBinding': 'EXAMPLE_EVENTS_V9',
                    'extensions': {
                        'a2aInspector': {
                            'profileVersion': 1,
                            'transport': 'websocket',
                            'subprotocol': 'example.events.v9',
                        }
                    },
                },
            ]
        }
    )

    assert declarations == [
        app.InspectorWebSocketInterface(
            index=1,
            url='wss://agent.example/events',
            protocol_binding='EXAMPLE_EVENTS_V9',
            subprotocol='example.events.v9',
        )
    ]


@pytest.mark.asyncio
@respx.mock
async def test_agent_card_endpoint_preserves_declared_extension():
    card_url = 'https://agent.example/.well-known/agent-card.json'
    card = {
        'name': 'Example',
        'description': 'Example agent',
        'version': '1.0',
        'capabilities': {},
        'defaultInputModes': ['text/plain'],
        'defaultOutputModes': ['text/plain'],
        'skills': [],
        'supportedInterfaces': [
            {
                'url': 'wss://agent.example/events',
                'protocolBinding': 'EXAMPLE_EVENTS',
                'extensions': {
                    'a2aInspector': {
                        'profileVersion': 1,
                        'transport': 'websocket',
                        'subprotocol': 'example.events.v1',
                    }
                },
            }
        ],
    }
    respx.get(card_url).respond(json=card)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app.app),
        base_url='http://inspector.test',
    ) as client:
        response = await client.post(
            '/agent-card', json={'url': card_url, 'sid': 'test-sid'}
        )

    assert response.status_code == 200
    assert response.json()['card'] == card


@pytest.mark.parametrize(
    'profile',
    [
        {'profileVersion': 1, 'transport': 'websocket'},
        {
            'profileVersion': 1,
            'transport': 'websocket',
            'subprotocol': '',
        },
        {
            'profileVersion': 2,
            'transport': 'websocket',
            'subprotocol': 'example.events.v1',
        },
    ],
)
def test_incomplete_or_unknown_profile_versions_are_not_selectable(profile):
    declarations = app._declared_inspector_websocket_interfaces(
        {
            'supportedInterfaces': [
                {
                    'url': 'wss://agent.example/events',
                    'protocolBinding': 'EXAMPLE_EVENTS',
                    'extensions': {'a2aInspector': profile},
                }
            ]
        }
    )

    assert declarations == []


class FakeConnection:
    def __init__(self):
        self.sent: list[str | bytes] = []

    async def send(self, frame: str | bytes) -> None:
        self.sent.append(frame)

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_bridge_relays_explicit_text_and_binary_frames(monkeypatch):
    connection = FakeConnection()
    receive_task = asyncio.create_task(asyncio.sleep(60))
    app.websocket_bridges['sid'] = app.WebSocketBridge(
        connection=connection, receive_task=receive_task
    )
    emitted: list[tuple[str, dict[str, object]]] = []

    async def emit(name, data, **_):
        emitted.append((name, data))

    monkeypatch.setattr(app.sio, 'emit', emit)

    await app.handle_send_websocket_frame(
        'sid', {'frame': {'type': 'text', 'data': '{"custom":"frame"}'}}
    )
    await app.handle_send_websocket_frame(
        'sid', {'frame': {'type': 'binary', 'data': 'AAE='}}
    )

    assert connection.sent == ['{"custom":"frame"}', b'\x00\x01']
    assert [item[0] for item in emitted] == ['debug_log', 'debug_log']

    await app._close_websocket_bridge('sid')


@pytest.mark.asyncio
@respx.mock
async def test_declared_websocket_url_and_subprotocol_are_bridged(monkeypatch):
    received = asyncio.Event()
    relayed = asyncio.Event()
    server_frames: list[str] = []
    emitted: list[tuple[str, dict[str, object]]] = []

    async def agent(connection):
        assert connection.subprotocol == 'example.events.v1'
        frame = await connection.recv()
        server_frames.append(frame)
        received.set()
        await connection.send('{"event":"declared"}')

    async with serve(
        agent,
        '127.0.0.1',
        0,
        subprotocols=['example.events.v1'],
    ) as server:
        port = server.sockets[0].getsockname()[1]
        card_url = 'https://agent.example/.well-known/agent-card.json'
        respx.get(card_url).respond(
            json={
                'supportedInterfaces': [
                    {
                        'url': f'ws://127.0.0.1:{port}/not-derived',
                        'protocolBinding': 'EXAMPLE_EVENTS',
                        'extensions': {
                            'a2aInspector': {
                                'profileVersion': 1,
                                'transport': 'websocket',
                                'subprotocol': 'example.events.v1',
                            }
                        },
                    }
                ]
            }
        )

        async def emit(name, data, **_):
            emitted.append((name, data))
            if name == 'websocket_frame':
                relayed.set()

        monkeypatch.setattr(app.sio, 'emit', emit)

        await app.handle_initialize_websocket_bridge(
            'sid',
            {
                'url': card_url,
                'customHeaders': {},
                'interfaceIndex': 0,
            },
        )
        await app.handle_send_websocket_frame(
            'sid', {'frame': {'type': 'text', 'data': '{"request":"opaque"}'}}
        )

        await asyncio.wait_for(received.wait(), timeout=1)
        await asyncio.wait_for(relayed.wait(), timeout=1)

    assert server_frames == ['{"request":"opaque"}']
    assert (
        'websocket_frame',
        {'type': 'text', 'data': '{"event":"declared"}'},
    ) in emitted
    await app._close_websocket_bridge('sid')
