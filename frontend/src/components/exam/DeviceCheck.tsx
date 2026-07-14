"use client";

import { useEffect, useState } from "react";
import { api, errorText } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { CheckCircle2, Circle, XCircle } from "lucide-react";

interface CheckState {
  camera: boolean | null;
  microphone: boolean | null;
  network: boolean | null;
  fullscreen: boolean | null;
}

const LABELS: Record<keyof CheckState, string> = {
  camera: "Camera access",
  microphone: "Microphone access",
  network: "Internet connection",
  fullscreen: "Full-screen capability",
};

export function DeviceCheck({
  rules,
  onReady,
}: {
  rules: string[];
  onReady: () => void;
}) {
  const [checks, setChecks] = useState<CheckState>({
    camera: null,
    microphone: null,
    network: null,
    fullscreen: null,
  });
  const [acknowledged, setAcknowledged] = useState(false);
  const [running, setRunning] = useState(false);

  const allPassed = Object.values(checks).every((v) => v === true);

  async function runChecks() {
    setRunning(true);
    const next: CheckState = { camera: false, microphone: false, network: false, fullscreen: false };
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
      next.camera = stream.getVideoTracks().length > 0;
      next.microphone = stream.getAudioTracks().length > 0;
      stream.getTracks().forEach((track) => track.stop());
    } catch {
      // camera/microphone stay false
    }
    try {
      const started = performance.now();
      await fetch(`${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api/v1/health`, {
        cache: "no-store",
      });
      next.network = performance.now() - started < 5000;
    } catch {
      next.network = false;
    }
    next.fullscreen = !!document.documentElement.requestFullscreen;
    setChecks(next);
    setRunning(false);
    try {
      await api("/exam/device-check", {
        token: "candidate",
        body: {
          camera: next.camera,
          microphone: next.microphone,
          network_mbps: next.network ? 1 : 0,
          browser: navigator.userAgent,
          fullscreen: next.fullscreen ?? false,
        },
      });
    } catch (error) {
      toast.error(errorText(error));
    }
  }

  useEffect(() => {
    runChecks();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function icon(value: boolean | null) {
    if (value === null) return <Circle className="h-4 w-4 text-muted-foreground animate-pulse" />;
    return value ? (
      <CheckCircle2 className="h-4 w-4 text-foreground" />
    ) : (
      <XCircle className="h-4 w-4 text-destructive" />
    );
  }

  return (
    <div className="mx-auto max-w-xl space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>System check</CardTitle>
          <CardDescription>
            All checks must pass before you can start the assessment.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {(Object.keys(checks) as (keyof CheckState)[]).map((key) => (
            <div key={key} className="flex items-center justify-between rounded-md border p-3">
              <span className="text-sm">{LABELS[key]}</span>
              {icon(checks[key])}
            </div>
          ))}
          <Button variant="outline" size="sm" onClick={runChecks} disabled={running}>
            {running ? "Checking…" : "Re-run checks"}
          </Button>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Exam rules</CardTitle>
          <CardDescription>Read carefully — these are enforced and recorded.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <ul className="list-disc pl-5 text-sm space-y-1">
            {rules.map((rule, index) => (
              <li key={index}>{rule}</li>
            ))}
          </ul>
          <label className="flex items-start gap-2 text-sm">
            <input
              type="checkbox"
              className="mt-1"
              checked={acknowledged}
              onChange={(e) => setAcknowledged(e.target.checked)}
            />
            I have read and accept the exam rules and monitoring described above.
          </label>
          <Button
            className="w-full"
            disabled={!allPassed || !acknowledged}
            onClick={async () => {
              try {
                await document.documentElement.requestFullscreen();
              } catch {
                // full-screen refusal is recorded as a proctoring event once the exam starts
              }
              onReady();
            }}
          >
            Start assessment
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
