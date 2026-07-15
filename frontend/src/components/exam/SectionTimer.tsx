"use client";

import { useEffect, useRef, useState } from "react";
import { TimerIcon } from "lucide-react";
import { getToken } from "@/lib/api";
import { cn } from "@/lib/utils";

interface TimerMessage {
  status: string;
  current_section_id: string | null;
  remaining_seconds: number;
}

export function SectionTimer({
  sessionId,
  sectionId,
  onStateChange,
}: {
  sessionId: string;
  sectionId: string;
  onStateChange: () => unknown | Promise<unknown>;
}) {
  const [remainingSeconds, setRemainingSeconds] = useState<number | null>(null);
  const callbackRef = useRef(onStateChange);
  callbackRef.current = onStateChange;

  useEffect(() => {
    let socket: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let stopped = false;

    const connect = () => {
      const token = getToken("candidate");
      if (!token || stopped) return;
      const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
      const wsBase = apiBase.replace(/^http/, "ws");
      socket = new WebSocket(
        `${wsBase}/api/v1/exam/timer?token=${encodeURIComponent(token)}`
      );
      socket.onmessage = (event) => {
        const message = JSON.parse(event.data) as TimerMessage;
        setRemainingSeconds(message.remaining_seconds);
        if (message.status !== "active" || message.current_section_id !== sectionId) {
          void callbackRef.current();
        }
      };
      socket.onclose = (event) => {
        if (!stopped && event.code !== 1000) {
          reconnectTimer = setTimeout(connect, 1000);
        }
      };
    };

    setRemainingSeconds(null);
    connect();
    return () => {
      stopped = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      socket?.close();
    };
  }, [sectionId, sessionId]);

  const minutes = remainingSeconds === null ? null : Math.floor(remainingSeconds / 60);
  const seconds = remainingSeconds === null ? null : remainingSeconds % 60;
  const low = remainingSeconds !== null && remainingSeconds < 120;

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 font-mono text-sm font-semibold tabular-nums transition-colors",
        low
          ? "border-destructive/40 bg-destructive/10 text-destructive"
          : "border-border bg-muted/50 text-foreground"
      )}
      data-testid="section-timer"
    >
      <TimerIcon className={cn("h-4 w-4", low && "animate-pulse")} />
      {minutes === null || seconds === null
        ? "--:--"
        : `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`}
    </span>
  );
}
