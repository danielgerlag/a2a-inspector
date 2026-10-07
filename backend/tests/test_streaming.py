"""Tests for standard A2A streaming inspector actions."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend import app as inspector


class StreamingClient:
    """A minimal SDK client double that records standard stream requests."""

    def __init__(self) -> None:
        self.message_requests = []
        self.subscription_requests = []
        self.subscription_contexts = []

    async def send_message(self, request):
        self.message_requests.append(request)
        yield object()

    async def subscribe(self, request, context=None):
        self.subscription_requests.append(request)
        self.subscription_contexts.append(context)
        yield object()


def make_session(client: StreamingClient) -> inspector.ClientSession:
    return inspector.ClientSession(
        httpx_client=AsyncMock(),
        message_client=client,
        streaming_client=client,
        agent_card=SimpleNamespace(
            capabilities=SimpleNamespace(streaming=True)
        ),
        transport='JSONRPC',
    )


def test_client_config_can_preserve_send_message_or_enable_streaming():
    assert inspector._make_client_config(streaming=False).streaming is False
    assert inspector._make_client_config(streaming=True).streaming is True


@pytest.mark.asyncio
async def test_streaming_message_uses_sdk_streaming_client(monkeypatch):
    client = StreamingClient()
    inspector.clients['socket-1'] = make_session(client)
    process_response = AsyncMock()
    emit = AsyncMock()
    monkeypatch.setattr(inspector, '_process_a2a_response', process_response)
    monkeypatch.setattr(inspector.sio, 'emit', emit)

    try:
        await inspector.handle_send_streaming_message(
            'socket-1',
            {
                'id': 'message-1',
                'message': 'watch this task',
                'metadata': {},
                'attachments': [],
            },
        )
    finally:
        inspector.clients.pop('socket-1', None)

    assert len(client.message_requests) == 1
    assert client.message_requests[0].message.message_id == 'message-1'
    process_response.assert_awaited_once()
    assert any(
        call.args[0] == 'debug_log'
        and call.args[1]['data']['method'] == 'SendStreamingMessage'
        for call in emit.await_args_list
    )


@pytest.mark.asyncio
async def test_subscribe_to_task_uses_sdk_subscribe(monkeypatch):
    client = StreamingClient()
    inspector.clients['socket-1'] = make_session(client)
    process_response = AsyncMock()
    emit = AsyncMock()
    monkeypatch.setattr(inspector, '_process_a2a_response', process_response)
    monkeypatch.setattr(inspector.sio, 'emit', emit)

    try:
        await inspector.handle_subscribe_to_task(
            'socket-1', {'taskId': 'task-42'}
        )
    finally:
        inspector.clients.pop('socket-1', None)

    assert len(client.subscription_requests) == 1
    assert client.subscription_requests[0].id == 'task-42'
    process_response.assert_awaited_once()
    assert any(
        call.args[0] == 'debug_log'
        and call.args[1]['data']['method'] == 'SubscribeToTask'
        for call in emit.await_args_list
    )


@pytest.mark.asyncio
async def test_subscribe_to_task_sends_last_event_id(monkeypatch):
    client = StreamingClient()
    inspector.clients['socket-1'] = make_session(client)
    monkeypatch.setattr(inspector, '_process_a2a_response', AsyncMock())
    monkeypatch.setattr(inspector.sio, 'emit', AsyncMock())

    try:
        await inspector.handle_subscribe_to_task(
            'socket-1', {'taskId': 'task-42', 'lastEventId': '17'}
        )
    finally:
        inspector.clients.pop('socket-1', None)

    assert client.subscription_contexts[0].service_parameters['Last-Event-ID'] == '17'
