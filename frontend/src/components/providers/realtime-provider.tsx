"use client";

import * as React from "react";
import { API_BASE, getToken } from "@/lib/api";
import type { RealtimeEvent } from "@/types/api";

interface RealtimeContextValue {
  connected: boolean;
  lastEvent: RealtimeEvent | null;
  events: RealtimeEvent[];
  subscribe: (handler: (event: RealtimeEvent) => void) => () => void;
}

const RealtimeContext = React.createContext<RealtimeContextValue | null>(null);

function wsUrl(): string {
  const base = API_BASE.replace(/^http/, "ws");
  const token = getToken();
  return `${base}/ws/events${token ? `?token=${encodeURIComponent(token)}` : ""}`;
}

export function RealtimeProvider({ children }: { children: React.ReactNode }) {
  const [connected, setConnected] = React.useState(false);
  const [events, setEvents] = React.useState<RealtimeEvent[]>([]);
  const [lastEvent, setLastEvent] = React.useState<RealtimeEvent | null>(null);
  const handlers = React.useRef(new Set<(event: RealtimeEvent) => void>());
  const socketRef = React.useRef<WebSocket | null>(null);
  const retryRef = React.useRef(0);

  React.useEffect(() => {
    let closed = false;
    let timer: ReturnType<typeof setTimeout>;

    const connect = () => {
      if (closed) return;
      try {
        const socket = new WebSocket(wsUrl());
        socketRef.current = socket;

        socket.onopen = () => {
          setConnected(true);
          retryRef.current = 0;
        };
        socket.onmessage = (message) => {
          try {
            const event = JSON.parse(message.data) as RealtimeEvent;
            if (event.topic === "system.pong" || event.topic === "system.connected") return;
            setLastEvent(event);
            setEvents((prev) => [event, ...prev].slice(0, 100));
            handlers.current.forEach((handler) => handler(event));
          } catch {
            /* ignore malformed frames */
          }
        };
        socket.onclose = () => {
          setConnected(false);
          if (closed) return;
          retryRef.current = Math.min(retryRef.current + 1, 6);
          timer = setTimeout(connect, 1000 * 2 ** retryRef.current);
        };
        socket.onerror = () => socket.close();
      } catch {
        timer = setTimeout(connect, 5000);
      }
    };

    connect();
    return () => {
      closed = true;
      clearTimeout(timer);
      socketRef.current?.close();
    };
  }, []);

  const subscribe = React.useCallback((handler: (event: RealtimeEvent) => void) => {
    handlers.current.add(handler);
    return () => handlers.current.delete(handler);
  }, []);

  const value = React.useMemo(
    () => ({ connected, lastEvent, events, subscribe }),
    [connected, lastEvent, events, subscribe],
  );

  return <RealtimeContext.Provider value={value}>{children}</RealtimeContext.Provider>;
}

export function useRealtime(): RealtimeContextValue {
  const ctx = React.useContext(RealtimeContext);
  if (!ctx) throw new Error("useRealtime must be used inside RealtimeProvider");
  return ctx;
}
