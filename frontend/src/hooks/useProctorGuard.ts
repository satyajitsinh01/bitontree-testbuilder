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
  | "capture_failed"
  | "devtools_open"
  | "window_resize"
  | "print_screen_attempt"
  | "blocked_shortcut";

interface ProctorEvent {
  kind: EventKind;
  occurred_at: string;
  detail?: Record<string, unknown>;
}

const FLUSH_INTERVAL_MS = 4000;
const SCREENSHOT_INTERVAL_MS = 5000;
const DEVTOOLS_CHECK_INTERVAL_MS = 1000;
const DEVTOOLS_GAP_THRESHOLD_PX = 160;

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
    const baseline = (() => {
      try {
        const stored = JSON.parse(sessionStorage.getItem("exam-start-viewport") ?? "null");
        if (typeof stored?.width === "number" && typeof stored?.height === "number") {
          return stored as { width: number; height: number };
        }
      } catch {
        // Fall through to the current viewport when stored data is unavailable.
      }
      return { width: window.innerWidth, height: window.innerHeight };
    })();
    const initialChromeGap = {
      width: Math.max(0, window.outerWidth - window.innerWidth),
      height: Math.max(0, window.outerHeight - window.innerHeight),
    };
    let resizeFlagged = false;
    let devtoolsFlagged = false;
    const onResize = () => {
      const tooSmall = window.innerWidth < baseline.width || window.innerHeight < baseline.height;
      if (tooSmall && !resizeFlagged) {
        resizeFlagged = true;
        push("window_resize", {
          initial_width: baseline.width,
          initial_height: baseline.height,
          current_width: window.innerWidth,
          current_height: window.innerHeight,
        });
        onWarning("Reducing the exam window size is not allowed and was red-flagged.");
      } else if (!tooSmall) {
        resizeFlagged = false;
      }
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "PrintScreen") {
        event.preventDefault();
        push("print_screen_attempt");
        onWarning("Screenshot attempts are not allowed and were red-flagged.");
        return;
      }
      const blocked =
        event.key === "F12" ||
        (event.ctrlKey && event.shiftKey && ["I", "J", "C"].includes(event.key.toUpperCase())) ||
        (event.ctrlKey && event.key.toUpperCase() === "U");
      if (blocked) {
        event.preventDefault();
        event.stopPropagation();
        push("blocked_shortcut", { key: event.key });
        onWarning("Developer tools are disabled and this attempt was red-flagged.");
      }
    };
    const onContextMenu = (event: MouseEvent) => event.preventDefault();

    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("blur", onBlur);
    document.addEventListener("fullscreenchange", onFullscreen);
    document.addEventListener("copy", onCopy);
    document.addEventListener("paste", onPaste);
    window.addEventListener("resize", onResize);
    window.addEventListener("keydown", onKeyDown, true);
    document.addEventListener("contextmenu", onContextMenu);

    const devtoolsChecker = setInterval(() => {
      const widthGap = window.outerWidth - window.innerWidth - initialChromeGap.width;
      const heightGap = window.outerHeight - window.innerHeight - initialChromeGap.height;
      const suspected = widthGap > DEVTOOLS_GAP_THRESHOLD_PX || heightGap > DEVTOOLS_GAP_THRESHOLD_PX;
      if (suspected && !devtoolsFlagged) {
        devtoolsFlagged = true;
        push("devtools_open", { width_gap: widthGap, height_gap: heightGap });
        onWarning("Developer tools were detected and red-flagged.");
      } else if (!suspected) {
        devtoolsFlagged = false;
      }
    }, DEVTOOLS_CHECK_INTERVAL_MS);

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
      window.removeEventListener("resize", onResize);
      window.removeEventListener("keydown", onKeyDown, true);
      document.removeEventListener("contextmenu", onContextMenu);
      clearInterval(flusher);
      clearInterval(devtoolsChecker);
      if (screenshotTimer) clearInterval(screenshotTimer);
      stream.current?.getTracks().forEach((track) => track.stop());
    };
  }, [active, push, onWarning]);
}
