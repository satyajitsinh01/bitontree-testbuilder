"use client";

import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";
import { TimerIcon } from "lucide-react";

/** Server-authoritative countdown: renders (deadline - now - drift) and never
 * trusts the local clock alone. onExpire fires once at zero. */
export function SectionTimer({
  deadlineAt,
  serverNow,
  onExpire,
}: {
  deadlineAt: string;
  serverNow: string;
  onExpire: () => void;
}) {
  const [remaining, setRemaining] = useState<number>(() => compute());

  function compute() {
    const drift = new Date(serverNow + "Z").getTime() - Date.now();
    return Math.max(0, new Date(deadlineAt + "Z").getTime() - (Date.now() + drift));
  }

  useEffect(() => {
    const timer = setInterval(() => {
      const next = compute();
      setRemaining(next);
      if (next <= 0) {
        clearInterval(timer);
        onExpire();
      }
    }, 1000);
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
        "inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 font-mono text-sm font-semibold",
        low ? "border-destructive text-destructive animate-pulse" : "border-border"
      )}
      data-testid="section-timer"
    >
      <TimerIcon className="h-4 w-4" />
      {String(minutes).padStart(2, "0")}:{String(seconds).padStart(2, "0")}
    </span>
  );
}
