"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { api, ApiError, setToken } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Clock, MonitorX, XCircle } from "lucide-react";

interface LoginOut {
  access_token: string;
  assignment_summary: {
    candidate_name: string;
    assessment_title: string;
    window_start_at: string;
    window_end_at: string;
    has_active_session: boolean;
  };
}

type Blocker =
  | { kind: "not_started"; startsAt: string }
  | { kind: "expired" }
  | { kind: "session_active" }
  | null;

export default function CandidateLogin() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [blocker, setBlocker] = useState<Blocker>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setBlocker(null);
    try {
      const data = await api<LoginOut>("/auth/candidate/login", {
        body: { username, password },
      });
      setToken("candidate", data.access_token);
      window.localStorage.setItem(
        "tb_candidate_summary",
        JSON.stringify(data.assignment_summary)
      );
      router.push("/candidate/exam");
    } catch (error) {
      if (error instanceof ApiError) {
        if (error.code === "window_not_started") {
          const startsAt = (error.payload.starts_at as string | undefined) ?? "";
          setBlocker({ kind: "not_started", startsAt });
          return;
        }
        if (error.code === "window_expired") {
          setBlocker({ kind: "expired" });
          return;
        }
        if (error.code === "session_active") {
          setBlocker({ kind: "session_active" });
          return;
        }
      }
      toast.error("Invalid credentials. Check your invitation email.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="min-h-screen flex items-center justify-center bg-muted/40 p-6">
      <div className="w-full max-w-sm space-y-4">
        <Card>
          <CardHeader>
            <CardTitle>Candidate sign in</CardTitle>
            <CardDescription>
              Use the username and password from your invitation email.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={submit} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="username">Username</Label>
                <Input
                  id="username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  required
                  autoComplete="username"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="password">Password</Label>
                <Input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
              </div>
              <Button type="submit" className="w-full" disabled={busy}>
                {busy ? "Signing in…" : "Sign in"}
              </Button>
            </form>
          </CardContent>
        </Card>

        {blocker?.kind === "not_started" && (
          <Alert>
            <Clock className="h-4 w-4" />
            <AlertTitle>Your test will start soon.</AlertTitle>
            <AlertDescription>
              The assessment window opens at{" "}
              {blocker.startsAt
                ? new Date(blocker.startsAt + "Z").toLocaleString()
                : "the scheduled time"}
              . Please come back then.
            </AlertDescription>
          </Alert>
        )}
        {blocker?.kind === "expired" && (
          <Alert variant="destructive">
            <XCircle className="h-4 w-4" />
            <AlertTitle>Assessment window has expired.</AlertTitle>
            <AlertDescription>
              Contact the recruiter if you believe this is a mistake.
            </AlertDescription>
          </Alert>
        )}
        {blocker?.kind === "session_active" && (
          <Alert variant="destructive">
            <MonitorX className="h-4 w-4" />
            <AlertTitle>Already active on another device</AlertTitle>
            <AlertDescription>
              This assessment is open on another device or tab. Close it and try again in
              a minute, or ask the recruiter to reset your session.
            </AlertDescription>
          </Alert>
        )}
      </div>
    </main>
  );
}
