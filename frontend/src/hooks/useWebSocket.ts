import { useRef } from "react";

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null);

  const connect = (url: string) => {
    const state = wsRef.current?.readyState;
    if (state === WebSocket.OPEN || state === WebSocket.CONNECTING) return wsRef.current!;
    wsRef.current?.close();
    const ws = new WebSocket(url);
    ws.onerror = (e) => console.error('[WS] error', e);
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
