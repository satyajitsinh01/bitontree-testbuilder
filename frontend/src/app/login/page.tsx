"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { api, ApiError, setRefreshToken, setToken } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { CheckCircle2, ClipboardList, Clock, MonitorX, XCircle } from "lucide-react";

interface UnifiedLoginOut {
  kind: "admin" | "candidate";
  access_token: string;
  refresh_token?: string;
  user?: { id: string; email: string; full_name: string };
  roles?: string[];
  assignment_summary?: {
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
  | { kind: "already_submitted" }
  | null;

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [blocker, setBlocker] = useState<Blocker>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setBlocker(null);
    try {
      const data = await api<UnifiedLoginOut>("/auth/login", {
        body: { email, password },
      });
      if (data.kind === "admin") {
        setToken("admin", data.access_token);
        window.localStorage.setItem("tb_admin_roles", JSON.stringify(data.roles ?? []));
        window.localStorage.setItem("tb_admin_name", data.user?.full_name ?? "");
        router.push("/admin");
      } else {
        setToken("candidate", data.access_token);
        setRefreshToken("candidate", data.refresh_token ?? null);
        window.localStorage.setItem(
          "tb_candidate_summary",
          JSON.stringify(data.assignment_summary ?? {})
        );
        router.push("/candidate/exam");
      }
    } catch (error) {
      if (error instanceof ApiError) {
        if (error.code === "window_not_started") {
          setBlocker({
            kind: "not_started",
            startsAt: (error.payload.starts_at as string | undefined) ?? "",
          });
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
        if (error.code === "already_submitted") {
          setBlocker({ kind: "already_submitted" });
          return;
        }
      }
      toast.error("Invalid email or password.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="min-h-screen flex items-center justify-center bg-gradient-to-br from-muted/60 via-background to-accent/40 p-6">
      <div className="w-full max-w-sm space-y-4">
        <div className="flex flex-col items-center gap-2 pb-2">
          <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-lg shadow-primary/15">
            <ClipboardList className="h-5 w-5" />
          </span>
          <h1 className="text-xl font-semibold tracking-tight">TestBuilder</h1>
        </div>
        <Card className="shadow-xl shadow-foreground/5">
          <CardHeader>
            <CardTitle>Sign in</CardTitle>
            <CardDescription>
              Admins use their account email. Candidates use the email and password
              from their invitation.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={submit} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  autoComplete="email"
                  placeholder="you@example.com"
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
                  autoComplete="current-password"
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
              This assessment is open on another device or tab. Close it and try again
              in a minute, or ask the recruiter to reset your session.
            </AlertDescription>
          </Alert>
        )}
        {blocker?.kind === "already_submitted" && (
          <Alert>
            <CheckCircle2 className="h-4 w-4" />
            <AlertTitle>Assessment already submitted</AlertTitle>
            <AlertDescription>
              You have already completed this assessment, so these credentials are no
              longer valid. The recruiting team will contact you with results.
            </AlertDescription>
          </Alert>
        )}
      </div>
    </main>
  );
}
