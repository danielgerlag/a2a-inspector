export interface InspectorWebSocketInterface {
  index: number;
  url: string;
  protocolBinding: string;
  subprotocol: string;
}

type JsonObject = Record<string, unknown>;

function isObject(value: unknown): value is JsonObject {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isWebSocketUrl(value: string): boolean {
  return /^(?:ws|wss):\/\/[^/?#]+(?:[/?#]|$)/.test(value);
}

/**
 * Finds only interfaces that explicitly opt into version 1 of the Inspector
 * WebSocket profile. The inspector never derives a URL or a subprotocol.
 */
export function discoverInspectorWebSocketInterfaces(
  card: unknown,
): InspectorWebSocketInterface[] {
  if (!isObject(card) || !Array.isArray(card.supportedInterfaces)) {
    return [];
  }

  return card.supportedInterfaces.flatMap((candidate, index) => {
    if (!isObject(candidate) || !isObject(candidate.extensions)) {
      return [];
    }

    const profile = candidate.extensions.a2aInspector;
    if (!isObject(profile)) {
      return [];
    }

    const url = candidate.url;
    const protocolBinding = candidate.protocolBinding;
    const profileVersion = profile.profileVersion;
    const transport = profile.transport;
    const subprotocol = profile.subprotocol;

    if (
      typeof url !== 'string' ||
      !isWebSocketUrl(url) ||
      typeof protocolBinding !== 'string' ||
      typeof profileVersion !== 'number' ||
      profileVersion !== 1 ||
      transport !== 'websocket' ||
      typeof subprotocol !== 'string' ||
      subprotocol.length === 0
    ) {
      return [];
    }

    return [{index, url, protocolBinding, subprotocol}];
  });
}
