import { useCallback, useRef, useState } from "react";

export interface UseSimliAvatarReturn {
  startSession: (sessionToken: string) => Promise<void>;
  sendAudioChunk: (pcm: ArrayBuffer) => void;
  sendDone: () => void;
  sendSkip: () => void;
  videoRef: React.RefObject<HTMLVideoElement>;
  isConnected: boolean;
}

export function useSimliAvatar(): UseSimliAvatarReturn {
  const wsRef = useRef<WebSocket | null>(null);
  const pcRef = useRef<RTCPeerConnection | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  // Keep a ref alongside state so sendAudioChunk closure never goes stale
  const isConnectedRef = useRef(false);
  const [isConnected, setIsConnected] = useState(false);

  const startSession = useCallback(async (sessionToken: string) => {
    // Clean up any previous session
    wsRef.current?.close();
    pcRef.current?.close();
    isConnectedRef.current = false;
    setIsConnected(false);

    const pc = new RTCPeerConnection({
      iceServers: [{ urls: "stun:stun.l.google.com:19302" }],
    });
    pcRef.current = pc;

    // Receive Simli video+audio (audio is muted in JSX — local TTS is source of truth)
    pc.addTransceiver("video", { direction: "recvonly" });
    pc.addTransceiver("audio", { direction: "recvonly" });

    pc.ontrack = (event) => {
      if (videoRef.current && event.streams[0]) {
        videoRef.current.srcObject = event.streams[0];
      }
    };

    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);

    // Wait for ICE gathering to bundle all candidates into the SDP (3s timeout fallback)
    await new Promise<void>((resolve) => {
      if (pc.iceGatheringState === "complete") { resolve(); return; }
      const onchange = () => {
        if (pc.iceGatheringState === "complete") {
          pc.removeEventListener("icegatheringstatechange", onchange);
          resolve();
        }
      };
      pc.addEventListener("icegatheringstatechange", onchange);
      setTimeout(resolve, 3000);
    });

    const ws = new WebSocket(
      `wss://api.simli.ai/compose/webrtc/peer_to_peer?session_token=${sessionToken}`
    );
    wsRef.current = ws;

    ws.onopen = () => {
      ws.send(JSON.stringify({ type: "offer", sdp: pc.localDescription!.sdp }));
    };

    ws.onmessage = async (event) => {
      const raw = event.data as string;

      // "START" signals the avatar is ready to receive audio
      if (raw === "START") {
        isConnectedRef.current = true;
        setIsConnected(true);
        return;
      }

      try {
        const msg = JSON.parse(raw);
        if (msg.type === "answer") {
          await pc.setRemoteDescription(
            new RTCSessionDescription({ type: "answer", sdp: msg.sdp })
          );
        } else if (msg.type === "candidate" && msg.candidate) {
          await pc.addIceCandidate(
            new RTCIceCandidate({
              candidate: msg.candidate,
              sdpMid: msg.sdpMid ?? null,
              sdpMLineIndex: msg.sdpMLineIndex ?? null,
            })
          );
        }
      } catch {
        // Non-JSON message already handled above (e.g. future Simli events)
      }
    };

    ws.onerror = (e) => console.error("[SIMLI] WS error:", e);
    ws.onclose = () => {
      isConnectedRef.current = false;
      setIsConnected(false);
    };
  }, []);

  const sendAudioChunk = useCallback((pcm: ArrayBuffer) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN && isConnectedRef.current) {
      ws.send(new Uint8Array(pcm));
    }
  }, []);

  const sendDone = useCallback(() => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send("DONE");
    }
  }, []);

  const sendSkip = useCallback(() => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send("SKIP");
    }
  }, []);

  return { startSession, sendAudioChunk, sendDone, sendSkip, videoRef, isConnected };
}
