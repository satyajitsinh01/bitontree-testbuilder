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
  | "screen_capture_attempt"
  | "window_resized";

interface ProctorEvent {
  kind: EventKind;
  occurred_at: string;
  detail?: Record<string, unknown>;
}

const FLUSH_INTERVAL_MS = 4000;
const SCREENSHOT_INTERVAL_MS = 5000;
const DEVTOOLS_POLL_MS = 2000;
const DEVTOOLS_GAP_PX = 200;
const RESIZE_TOLERANCE_PX = 40;
const RESIZE_DEBOUNCE_MS = 600;

// devtools / view-source key combos to block outright
function isDevtoolsCombo(e: KeyboardEvent): string | null {
  if (e.key === "F12") return "F12";
  if (e.ctrlKey && e.shiftKey && ["I", "J", "C", "i", "j", "c"].includes(e.key))
    return `Ctrl+Shift+${e.key.toUpperCase()}`;
  if (e.ctrlKey && ["U", "u"].includes(e.key)) return "Ctrl+U";
  if (e.ctrlKey && ["S", "s", "P", "p"].includes(e.key))
    return `Ctrl+${e.key.toUpperCase()}`; // save page / print
  return null;
}

/** Client half of proctoring (FR-070..072): raises red-flag events for tab
 * switches, app/window switches, devtools & right-click attempts, screenshot
 * key presses, and window shrinking below its starting size; captures periodic
 * webcam snapshots. */
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

    // window size baseline: shrinking below the starting size is a red flag
    const baseline = { width: window.innerWidth, height: window.innerHeight };
    let resizeTimer: ReturnType<typeof setTimeout> | null = null;
    let devtoolsFlagged = false;

    const onVisibility = () => {
      if (document.hidden) {
        push("tab_switch");
        onWarning("Tab switch recorded as a red flag. Stay on the exam tab.");
      }
    };
    const onBlur = () => {
      push("window_blur");
      onWarning("Leaving the exam window is recorded as a red flag.");
    };
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
    const onContextMenu = (e: MouseEvent) => {
      e.preventDefault();
      push("devtools_open", { reason: "context_menu" });
      onWarning("Right-click is disabled during the exam.");
    };
    const onKeyDown = (e: KeyboardEvent) => {
      const combo = isDevtoolsCombo(e);
      if (combo) {
        e.preventDefault();
        e.stopPropagation();
        push("devtools_open", { reason: combo });
        onWarning("Developer tools are disabled — this attempt was recorded.");
      }
    };
    const onKeyUp = (e: KeyboardEvent) => {
      // PrintScreen only reliably fires on keyup
      if (e.key === "PrintScreen") {
        push("screen_capture_attempt", { reason: "print_screen" });
        navigator.clipboard?.writeText("").catch(() => {});
        onWarning("Screenshots are prohibited — this attempt was recorded.");
      }
    };
    const onResize = () => {
      if (resizeTimer) clearTimeout(resizeTimer);
      resizeTimer = setTimeout(() => {
        const shrunkWidth = window.innerWidth < baseline.width - RESIZE_TOLERANCE_PX;
        const shrunkHeight = window.innerHeight < baseline.height - RESIZE_TOLERANCE_PX;
        if (shrunkWidth || shrunkHeight) {
          push("window_resized", {
            baseline,
            current: { width: window.innerWidth, height: window.innerHeight },
          });
          onWarning(
            "The exam window must stay at its starting size — resizing was recorded."
          );
        }
      }, RESIZE_DEBOUNCE_MS);
    };

    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("blur", onBlur);
    document.addEventListener("fullscreenchange", onFullscreen);
    document.addEventListener("copy", onCopy);
    document.addEventListener("paste", onPaste);
    document.addEventListener("contextmenu", onContextMenu);
    window.addEventListener("keydown", onKeyDown, true);
    window.addEventListener("keyup", onKeyUp, true);
    window.addEventListener("resize", onResize);

    // best-effort docked-devtools heuristic: a large outer/inner gap appears
    // when the devtools panel opens inside the window
    const devtoolsPoll = setInterval(() => {
      const gapWidth = window.outerWidth - window.innerWidth;
      const gapHeight = window.outerHeight - window.innerHeight;
      const open = gapWidth > DEVTOOLS_GAP_PX || gapHeight > DEVTOOLS_GAP_PX;
      if (open && !devtoolsFlagged) {
        devtoolsFlagged = true;
        push("devtools_open", { reason: "window_gap", gapWidth, gapHeight });
        onWarning("Developer tools detected — this has been recorded as a red flag.");
      } else if (!open) {
        devtoolsFlagged = false;
      }
    }, DEVTOOLS_POLL_MS);

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
      document.removeEventListener("contextmenu", onContextMenu);
      window.removeEventListener("keydown", onKeyDown, true);
      window.removeEventListener("keyup", onKeyUp, true);
      window.removeEventListener("resize", onResize);
      clearInterval(devtoolsPoll);
      clearInterval(flusher);
      if (resizeTimer) clearTimeout(resizeTimer);
      if (screenshotTimer) clearInterval(screenshotTimer);
      stream.current?.getTracks().forEach((track) => track.stop());
    };
  }, [active, push, onWarning]);
}
