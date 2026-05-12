import { useRef } from "react";

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null);

  const connect = (url: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return wsRef.current;
    const ws = new WebSocket(url);
    ws.onerror = (e) => console.error('[WS] error', e);
    ws.onclose = (e) => console.log('[WS] closed', e.code, e.reason);
    wsRef.current = ws;
    return ws;
  };

  const sendJson = (data: object) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data));
    }
  };

  const sendBinary = (data: ArrayBuffer) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(data);
    }
  };

  const disconnect = () => {
    wsRef.current?.close();
    wsRef.current = null;
  };

  return { connect, disconnect, sendJson, sendBinary, wsRef };
}
