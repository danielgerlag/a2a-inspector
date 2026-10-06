import {describe, expect, it} from 'vitest';

import {discoverInspectorWebSocketInterfaces} from '../src/inspector-profile';

describe('discoverInspectorWebSocketInterfaces', () => {
  it('retains a declared custom WebSocket interface without binding-specific rules', () => {
    const interfaces = discoverInspectorWebSocketInterfaces({
      supportedInterfaces: [
        {
          url: 'https://agent.example/a2a',
          protocolBinding: 'JSONRPC',
        },
        {
          url: 'wss://agent.example/custom/live',
          protocolBinding: 'ACME_LIVE_EVENTS',
          extensions: {
            a2aInspector: {
              profileVersion: 1,
              transport: 'websocket',
              subprotocol: 'acme.live.events.v1',
            },
          },
        },
      ],
    });

    expect(interfaces).toEqual([
      {
        index: 1,
        url: 'wss://agent.example/custom/live',
        protocolBinding: 'ACME_LIVE_EVENTS',
        subprotocol: 'acme.live.events.v1',
      },
    ]);
  });

  it('does not infer a WebSocket binding from incomplete declarations', () => {
    const interfaces = discoverInspectorWebSocketInterfaces({
      supportedInterfaces: [
        {
          url: 'wss://agent.example/live',
          protocolBinding: 'CUSTOM',
          extensions: {
            a2aInspector: {
              profileVersion: 1,
              transport: 'websocket',
            },
          },
        },
      ],
    });

    expect(interfaces).toEqual([]);
  });
});
