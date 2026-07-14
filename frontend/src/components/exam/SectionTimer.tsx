"use client";

import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { TimerIcon } from "lucide-react";

/** Server-authoritative countdown: estimates server time as (local now + fixed
 * offset captured at mount) so it never trusts the raw local clock, yet still
 * ticks down every second. onExpire fires once at zero. */
export function SectionTimer({
  deadlineAt,
  serverNow,
  onExpire,
}: {
  deadlineAt: string;
  serverNow: string;
  onExpire: () => void;
}) {
  const deadlineMs = new Date(deadlineAt + "Z").getTime();
  // offset = serverEpoch - localEpoch, captured once per (deadline, serverNow).
  // estimated server now at any moment = Date.now() + offset.
  const offsetRef = useRef(0);
  const firedRef = useRef(false);

  const [remaining, setRemaining] = useState(() => {
    offsetRef.current = new Date(serverNow + "Z").getTime() - Date.now();
    return Math.max(0, deadlineMs - (Date.now() + offsetRef.current));
  });

  useEffect(() => {
    offsetRef.current = new Date(serverNow + "Z").getTime() - Date.now();
    firedRef.current = false;

    const tick = () => {
      const next = Math.max(0, deadlineMs - (Date.now() + offsetRef.current));
      setRemaining(next);
      if (next <= 0 && !firedRef.current) {
        firedRef.current = true;
        onExpire();
      }
    };
    tick(); // reflect the new section immediately
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deadlineAt, serverNow]);

  const totalSeconds = Math.floor(remaining / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  const low = totalSeconds < 120;

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
      {String(minutes).padStart(2, "0")}:{String(seconds).padStart(2, "0")}
    </span>
  );
}
