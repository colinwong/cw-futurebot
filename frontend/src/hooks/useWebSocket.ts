"use client";

import { useEffect, useCallback, useSyncExternalStore } from "react";
import type { WSMessage, WSEventType } from "@/lib/types";

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8002/api/ws";
const RECONNECT_DELAY = 3000;

type MessageHandler = (data: unknown) => void;

// Module-level singleton — shared across all components
let ws: WebSocket | null = null;
let wsConnected = false;
let reconnectTimer: ReturnType<typeof setTimeout> | undefined;
const handlers = new Map<WSEventType, Set<MessageHandler>>();
const connectedListeners = new Set<() => void>();

function notifyConnectedListeners() {
  connectedListeners.forEach((l) => l());
}

function connect() {
  if (ws?.readyState === WebSocket.OPEN || ws?.readyState === WebSocket.CONNECTING) return;

  ws = new WebSocket(WS_URL);

  ws.onopen = () => {
    wsConnected = true;
    notifyConnectedListeners();
    const pingInterval = setInterval(() => {
      if (ws?.readyState === WebSocket.OPEN) ws.send("ping");
    }, 30000);
    ws!.addEventListener("close", () => clearInterval(pingInterval));
  };

  ws.onmessage = (event) => {
    try {
      const msg: WSMessage = JSON.parse(event.data);
      const typeHandlers = handlers.get(msg.type);
      if (typeHandlers) {
        typeHandlers.forEach((handler) => handler(msg.data));
      }
    } catch {
      // Ignore malformed messages
    }
  };

  ws.onclose = () => {
    wsConnected = false;
    notifyConnectedListeners();
    reconnectTimer = setTimeout(connect, RECONNECT_DELAY);
  };

  ws.onerror = () => {
    ws?.close();
  };
}

// Start connection immediately on module load
if (typeof window !== "undefined") {
  connect();
}

export function useWebSocket() {
  const connected = useSyncExternalStore(
    (cb) => {
      connectedListeners.add(cb);
      return () => connectedListeners.delete(cb);
    },
    () => wsConnected,
    () => false, // server snapshot
  );

  const subscribe = useCallback((type: WSEventType, handler: MessageHandler) => {
    if (!handlers.has(type)) {
      handlers.set(type, new Set());
    }
    handlers.get(type)!.add(handler);

    return () => {
      handlers.get(type)?.delete(handler);
    };
  }, []);

  return { connected, subscribe };
}
