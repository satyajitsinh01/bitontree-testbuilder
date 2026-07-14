"use client";

import { useCallback, useEffect, useRef } from "react";
import { api } from "@/lib/api";

type EventKind =
  | "tab_switch"
  | "window_blur"
  | "fullscreen_exit"
  | "copy_attempt"
  | "paste_attempt"
  | "camera_lost"
  | "capture_failed";

interface ProctorEvent {
  kind: EventKind;
  occurred_at: string;
  detail?: Record<string, unknown>;
}

const FLUSH_INTERVAL_MS = 4000;
const SCREENSHOT_INTERVAL_MS = 5000;

/** Client half of proctoring (FR-070..072): raises events for tab switches,
 * blur, fullscreen exit, copy/paste; captures periodic webcam screenshots. */
export function useProctorGuard(active: boolean, onWarning: (message: string) => void) {
  const queue = useRef<ProctorEvent[]>([]);
  const stream = useRef<MediaStream | null>(null);
  const video = useRef<HTMLVideoElement | null>(null);

  const push = useCallback(
    (kind: EventKind, detail?: Record<string, unknown>) => {
      queue.current.push({
        kind,
        occurred_at: new Date().toISOString().replace("Z", ""),
        detail,
      });
    },
    []
  );

  useEffect(() => {
    if (!active) return;

    const onVisibility = () => {
      if (document.hidden) {
        push("tab_switch");
        onWarning("Tab switch recorded. Stay on the exam tab.");
      }
    };
    const onBlur = () => push("window_blur");
    const onFullscreen = () => {
      if (!document.fullscreenElement) {
        push("fullscreen_exit");
        onWarning("You left full-screen mode. This has been recorded.");
      }
    };
    const onCopy = (e: ClipboardEvent) => {
      e.preventDefault();
      push("copy_attempt");
      onWarning("Copying is disabled during the exam.");
    };
    const onPaste = (e: ClipboardEvent) => {
      e.preventDefault();
      push("paste_attempt");
      onWarning("Pasting is disabled during the exam.");
    };

    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("blur", onBlur);
    document.addEventListener("fullscreenchange", onFullscreen);
    document.addEventListener("copy", onCopy);
    document.addEventListener("paste", onPaste);

    const flusher = setInterval(async () => {
      if (queue.current.length === 0) return;
      const batch = queue.current.splice(0, queue.current.length);
      try {
        await api("/exam/proctoring/events", {
          token: "candidate",
          body: { events: batch },
        });
      } catch {
        queue.current.unshift(...batch); // retry next tick
      }
    }, FLUSH_INTERVAL_MS);

    // webcam screenshot loop (FR-072)
    let screenshotTimer: ReturnType<typeof setInterval> | null = null;
    (async () => {
      try {
        stream.current = await navigator.mediaDevices.getUserMedia({ video: true });
        const element = document.createElement("video");
        element.srcObject = stream.current;
        element.muted = true;
        await element.play();
        video.current = element;
        screenshotTimer = setInterval(async () => {
          const source = video.current;
          if (!source || source.videoWidth === 0) return;
          const canvas = document.createElement("canvas");
          canvas.width = 320;
          canvas.height = Math.round((320 / source.videoWidth) * source.videoHeight);
          const context = canvas.getContext("2d");
          if (!context) return;
          context.drawImage(source, 0, 0, canvas.width, canvas.height);
          const dataUrl = canvas.toDataURL("image/jpeg", 0.6);
          try {
            await api("/exam/proctoring/evidence", {
              token: "candidate",
              body: { image_base64: dataUrl, kind: "screenshot" },
            });
          } catch {
            push("capture_failed", { reason: "upload failed" });
          }
        }, SCREENSHOT_INTERVAL_MS);
        stream.current.getVideoTracks()[0]?.addEventListener("ended", () => {
          push("camera_lost");
          onWarning("Camera access lost — restore it to continue.");
        });
      } catch {
        push("camera_lost", { reason: "getUserMedia failed" });
      }
    })();

    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("blur", onBlur);
      document.removeEventListener("fullscreenchange", onFullscreen);
      document.removeEventListener("copy", onCopy);
      document.removeEventListener("paste", onPaste);
      clearInterval(flusher);
      if (screenshotTimer) clearInterval(screenshotTimer);
      stream.current?.getTracks().forEach((track) => track.stop());
    };
  }, [active, push, onWarning]);
}
