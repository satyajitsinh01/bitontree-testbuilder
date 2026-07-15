"use client";

import { useCallback, useEffect, useRef } from "react";
import type { RefObject } from "react";
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
  | "window_resized"
  | "screen_share_stopped";

interface ProctorEvent {
  kind: EventKind;
  occurred_at: string;
  detail?: Record<string, unknown>;
}

const FLUSH_INTERVAL_MS = 4000;
const SCREENSHOT_INTERVAL_MS = 5000;
const VIOLATION_CAPTURE_THROTTLE_MS = 1500;
const DEVTOOLS_POLL_MS = 2000;
const DEVTOOLS_GAP_PX = 200;
const RESIZE_TOLERANCE_PX = 40;
const RESIZE_DEBOUNCE_MS = 600;

// kinds that should trigger a full-screen violation screenshot
const VIOLATION_KINDS = new Set<EventKind>([
  "tab_switch",
  "window_blur",
  "fullscreen_exit",
  "copy_attempt",
  "paste_attempt",
  "devtools_open",
  "screen_capture_attempt",
  "window_resized",
  "camera_lost",
  "screen_share_stopped",
]);

function isDevtoolsCombo(e: KeyboardEvent): string | null {
  if (e.key === "F12") return "F12";
  if (e.ctrlKey && e.shiftKey && ["I", "J", "C", "i", "j", "c"].includes(e.key))
    return `Ctrl+Shift+${e.key.toUpperCase()}`;
  if (e.ctrlKey && ["U", "u"].includes(e.key)) return "Ctrl+U";
  if (e.ctrlKey && ["S", "s", "P", "p"].includes(e.key))
    return `Ctrl+${e.key.toUpperCase()}`;
  return null;
}

/** Client half of proctoring (FR-070..072): raises red-flag events for tab
 * switches, app/window switches, devtools & right-click attempts, screenshot
 * key presses, and window shrinking; captures periodic webcam frames AND a
 * full-screen screenshot on every violation (stored under .../violations). */
export function useProctorGuard(
  active: boolean,
  onWarning: (message: string) => void,
  screenStreamRef?: RefObject<MediaStream | null>
) {
  const queue = useRef<ProctorEvent[]>([]);
  const webcamStream = useRef<MediaStream | null>(null);
  const webcamVideo = useRef<HTMLVideoElement | null>(null);
  const screenVideo = useRef<HTMLVideoElement | null>(null);
  const lastViolationCapture = useRef(0);

  const captureViolationScreenshot = useCallback(async () => {
    const source = screenVideo.current;
    if (!source || source.videoWidth === 0) return;
    const now = Date.now();
    if (now - lastViolationCapture.current < VIOLATION_CAPTURE_THROTTLE_MS) return;
    lastViolationCapture.current = now;
    const maxWidth = 1280;
    const scale = Math.min(1, maxWidth / source.videoWidth);
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(source.videoWidth * scale);
    canvas.height = Math.round(source.videoHeight * scale);
    const context = canvas.getContext("2d");
    if (!context) return;
    context.drawImage(source, 0, 0, canvas.width, canvas.height);
    const dataUrl = canvas.toDataURL("image/jpeg", 0.7);
    try {
      await api("/exam/proctoring/evidence", {
        token: "candidate",
        body: { image_base64: dataUrl, kind: "screen" },
      });
    } catch {
      queue.current.push({
        kind: "capture_failed",
        occurred_at: new Date().toISOString().replace("Z", ""),
        detail: { reason: "violation screenshot upload failed" },
      });
    }
  }, []);

  const push = useCallback(
    (kind: EventKind, detail?: Record<string, unknown>) => {
      queue.current.push({
        kind,
        occurred_at: new Date().toISOString().replace("Z", ""),
        detail,
      });
      if (VIOLATION_KINDS.has(kind)) {
        void captureViolationScreenshot();
      }
    },
    [captureViolationScreenshot]
  );

  useEffect(() => {
    if (!active) return;

    // attach the (already-granted) screen stream to a hidden video for frame grabs
    const screenStream = screenStreamRef?.current ?? null;
    if (screenStream) {
      const element = document.createElement("video");
      element.srcObject = screenStream;
      element.muted = true;
      element.play().catch(() => {});
      screenVideo.current = element;
      screenStream.getVideoTracks()[0]?.addEventListener("ended", () => {
        push("screen_share_stopped");
        onWarning("Screen sharing was stopped — this is a red flag. Restart to continue.");
      });
    }

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
        queue.current.unshift(...batch);
      }
    }, FLUSH_INTERVAL_MS);

    // periodic webcam snapshots (kind "screenshot" -> .../webcam)
    let screenshotTimer: ReturnType<typeof setInterval> | null = null;
    (async () => {
      try {
        webcamStream.current = await navigator.mediaDevices.getUserMedia({ video: true });
        const element = document.createElement("video");
        element.srcObject = webcamStream.current;
        element.muted = true;
        await element.play();
        webcamVideo.current = element;
        screenshotTimer = setInterval(async () => {
          const source = webcamVideo.current;
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
            push("capture_failed", { reason: "webcam upload failed" });
          }
        }, SCREENSHOT_INTERVAL_MS);
        webcamStream.current.getVideoTracks()[0]?.addEventListener("ended", () => {
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
      webcamStream.current?.getTracks().forEach((track) => track.stop());
      screenVideo.current = null;
    };
  }, [active, push, onWarning, screenStreamRef]);
}
