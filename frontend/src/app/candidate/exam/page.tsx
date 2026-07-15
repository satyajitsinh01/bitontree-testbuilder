"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import {
  api,
  ApiError,
  errorText,
  getToken,
  setRefreshToken,
  setToken,
} from "@/lib/api";
import type { ExamQuestion, ExamState } from "@/lib/types";
import { useProctorGuard } from "@/hooks/useProctorGuard";
import { DeviceCheck } from "@/components/exam/DeviceCheck";
import { ProgressPalette } from "@/components/exam/ProgressPalette";
import { QuestionRenderer } from "@/components/exam/QuestionRenderer";
import { SectionTimer } from "@/components/exam/SectionTimer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { AlertTriangle, CheckCircle2 } from "lucide-react";

interface Summary {
  assessment_title: string;
  rules: string[];
  status: string;
}

type Phase = "loading" | "check" | "exam" | "done" | "ended";

const AUTOSAVE_DEBOUNCE_MS = 2000;

export default function ExamPage() {
  const router = useRouter();
  const [phase, setPhase] = useState<Phase>("loading");
  const [summary, setSummary] = useState<Summary | null>(null);
  const [state, setState] = useState<ExamState | null>(null);
  const [endedReason, setEndedReason] = useState("");

  const screenStreamRef = useRef<MediaStream | null>(null);
  const warn = useCallback((message: string) => toast.warning(message), []);
  useProctorGuard(phase === "exam", warn, screenStreamRef);

  // After the assessment ends, drop full screen and stop screen sharing.
  useEffect(() => {
    if (phase === "done" || phase === "ended") {
      if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
      screenStreamRef.current?.getTracks().forEach((track) => track.stop());
      screenStreamRef.current = null;
    }
  }, [phase]);

  const refreshState = useCallback(async () => {
    try {
      const next = await api<ExamState>("/exam/state", { token: "candidate" });
      setState(next);
      if (next.status === "submitted" || next.status === "auto_submitted") {
        setPhase("done");
      } else if (next.status === "terminated") {
        setEndedReason("Your session was ended by an administrator.");
        setPhase("ended");
      } else {
        setPhase("exam");
      }
      return next;
    } catch (error) {
      if (error instanceof ApiError && error.code === "no_active_session") {
        return null;
      }
      throw error;
    }
  }, []);

  useEffect(() => {
    if (!getToken("candidate")) {
      router.replace("/login");
      return;
    }
    (async () => {
      try {
        const info = await api<Summary>("/exam/summary", { token: "candidate" });
        setSummary(info);
        const existing = await refreshState();
        if (existing === null) setPhase("check");
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) {
          setEndedReason("Your assessment window has expired.");
          setPhase("ended");
        } else {
          toast.error(errorText(error));
        }
      }
    })();
  }, [router, refreshState]);

  async function startExam(screenStream: MediaStream) {
    screenStreamRef.current = screenStream;
    try {
      const next = await api<ExamState>("/exam/start", {
        token: "candidate",
        body: { acknowledged_rules: true },
      });
      setState(next);
      setPhase("exam");
    } catch (error) {
      if (error instanceof ApiError && error.code === "session_active") {
        await refreshState();
      } else {
        screenStream.getTracks().forEach((track) => track.stop());
        screenStreamRef.current = null;
        toast.error(errorText(error));
      }
    }
  }

  if (phase === "loading") {
    return (
      <main className="min-h-screen flex items-center justify-center">
        <p className="text-muted-foreground">Loading your assessment…</p>
      </main>
    );
  }

  if (phase === "check") {
    return (
      <main className="min-h-screen bg-muted/40 p-6">
        <div className="mx-auto max-w-xl mb-6 text-center space-y-1">
          <h1 className="text-2xl font-semibold">{summary?.assessment_title}</h1>
          <p className="text-sm text-muted-foreground">Pre-test system check</p>
        </div>
        <DeviceCheck rules={summary?.rules ?? []} onReady={startExam} />
      </main>
    );
  }

  if (phase === "done") {
    const timedOut = state?.status === "auto_submitted";
    return (
      <main className="min-h-screen flex items-center justify-center bg-muted/40 p-6">
        <Card className="max-w-md w-full text-center">
          <CardHeader>
            <CheckCircle2 className="h-12 w-12 text-foreground mx-auto" />
            <CardTitle>
              {timedOut ? "Time’s up — assessment submitted" : "Assessment submitted"}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-muted-foreground">
              {timedOut
                ? "Your test time has expired. Your assessment was submitted automatically, and your saved answers have been recorded."
                : "Your answers have been recorded successfully. You may close this window — the recruiting team will contact you with results."}
            </p>
            <Button
              variant="outline"
              onClick={() => {
                setToken("candidate", null);
                setRefreshToken("candidate", null);
                router.push("/login");
              }}
            >
              Sign out
            </Button>
          </CardContent>
        </Card>
      </main>
    );
  }

  if (phase === "ended") {
    return (
      <main className="min-h-screen flex items-center justify-center bg-muted/40 p-6">
        <Card className="max-w-md w-full text-center">
          <CardHeader>
            <CardTitle>Session ended</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-muted-foreground">{endedReason}</p>
            <Button variant="outline" onClick={() => router.push("/login")}>
              Back to sign in
            </Button>
          </CardContent>
        </Card>
      </main>
    );
  }

  if (!state) return null;
  return <ExamShell state={state} refreshState={refreshState} />;
}

function ExamShell({
  state,
  refreshState,
}: {
  state: ExamState;
  refreshState: () => Promise<ExamState | null>;
}) {
  const [questions, setQuestions] = useState<ExamQuestion[]>(state.questions);
  const [index, setIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<string, Record<string, unknown>>>(() =>
    Object.fromEntries(
      state.questions.map((q) => [q.session_question_id, q.saved_answer ?? {}])
    )
  );
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [fullscreenExited, setFullscreenExited] = useState(false);
  const [reentering, setReentering] = useState(false);
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    setQuestions(state.questions);
    setIndex(0);
    setAnswers(
      Object.fromEntries(
        state.questions.map((q) => [q.session_question_id, q.saved_answer ?? {}])
      )
    );
  }, [state.current_section_id, state.questions]);

  // Full-screen guard: leaving full screen raises a blocking warning modal
  // (the exit itself is also recorded as a red flag by the proctor guard).
  useEffect(() => {
    const onChange = () => setFullscreenExited(!document.fullscreenElement);
    document.addEventListener("fullscreenchange", onChange);
    setFullscreenExited(!document.fullscreenElement);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);

  async function reenterFullscreen() {
    setReentering(true);
    try {
      await document.documentElement.requestFullscreen();
      setFullscreenExited(false);
    } catch {
      toast.error("Could not enter full screen. Press F11 or allow full screen.");
    } finally {
      setReentering(false);
    }
  }

  const activeSection = state.sections.find(
    (s) => s.section_id === state.current_section_id
  );
  const question = questions[index];

  const scheduleAutosave = useCallback(
    (sqid: string, payload: Record<string, unknown>) => {
      if (saveTimer.current) clearTimeout(saveTimer.current);
      saveTimer.current = setTimeout(async () => {
        try {
          await api(`/exam/questions/${sqid}/answer`, {
            token: "candidate",
            method: "PUT",
            body: { payload },
          });
          setQuestions((prev) =>
            prev.map((q) =>
              q.session_question_id === sqid && q.state !== "marked_review"
                ? { ...q, state: "answered" }
                : q
            )
          );
        } catch {
          // retried on next keystroke or navigation checkpoint
        }
      }, AUTOSAVE_DEBOUNCE_MS);
    },
    []
  );

  function onAnswerChange(payload: Record<string, unknown>) {
    if (!question) return;
    setAnswers((prev) => ({ ...prev, [question.session_question_id]: payload }));
    scheduleAutosave(question.session_question_id, payload);
  }

  async function checkpointAndGo(nextIndex: number) {
    if (question) {
      if (saveTimer.current) clearTimeout(saveTimer.current);
      try {
        await api(`/exam/questions/${question.session_question_id}/checkpoint`, {
          token: "candidate",
          body: {
            kind: "next_question",
            payload: answers[question.session_question_id] ?? {},
          },
        });
        setQuestions((prev) =>
          prev.map((q) =>
            q.session_question_id === question.session_question_id &&
            Object.keys(answers[question.session_question_id] ?? {}).length > 0 &&
            q.state !== "marked_review"
              ? { ...q, state: "answered" }
              : q
          )
        );
      } catch (error) {
        if (error instanceof ApiError && error.code === "session_ended") {
          await refreshState();
          return;
        }
      }
    }
    setIndex(Math.max(0, Math.min(nextIndex, questions.length - 1)));
  }

  async function toggleMarkReview() {
    if (!question) return;
    try {
      const result = await api<{ state: ExamQuestion["state"] }>(
        `/exam/questions/${question.session_question_id}/mark-review`,
        { token: "candidate", method: "POST", body: {} }
      );
      setQuestions((prev) =>
        prev.map((q) =>
          q.session_question_id === question.session_question_id
            ? { ...q, state: result.state }
            : q
        )
      );
    } catch (error) {
      toast.error(errorText(error));
    }
  }

  async function submitSection() {
    if (!activeSection) return;
    try {
      await api(`/exam/sections/${activeSection.section_id}/submit`, {
        token: "candidate",
        method: "POST",
        body: {},
      });
      await refreshState();
    } catch (error) {
      toast.error(errorText(error));
    }
  }

  async function submitExam() {
    try {
      await api("/exam/submit", { token: "candidate", body: { confirm: true } });
      await refreshState();
    } catch (error) {
      toast.error(errorText(error));
      await refreshState();
    }
  }

  return (
    <main className="min-h-screen bg-muted/30 flex flex-col">
      <header className="sticky top-0 z-10 border-b bg-background px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="font-semibold">{activeSection?.name}</span>
          <Badge variant="outline">
            Section {(activeSection?.order_index ?? 0) + 1} of {state.sections.length}
          </Badge>
        </div>
        {activeSection?.deadline_at && (
          <SectionTimer
            sessionId={state.session_id}
            sectionId={activeSection.section_id}
            onStateChange={refreshState}
          />
        )}
      </header>

      <div className="flex-1 grid gap-6 p-6 lg:grid-cols-[1fr_240px] max-w-6xl w-full mx-auto">
        <Card className="min-h-[60vh]">
          <CardHeader className="flex flex-row items-start justify-between space-y-0">
            <div>
              <CardTitle className="text-lg">
                Q{index + 1}. {question?.title}
              </CardTitle>
              {question?.body && question.body !== question.title && (
                <p className="mt-1 text-sm text-muted-foreground whitespace-pre-wrap">
                  {question.body}
                </p>
              )}
            </div>
            <Badge variant="outline">{question?.points} pts</Badge>
          </CardHeader>
          <CardContent className="space-y-6">
            {question && (
              <QuestionRenderer
                key={question.session_question_id}
                question={question}
                answer={answers[question.session_question_id] ?? {}}
                onChange={onAnswerChange}
              />
            )}
            <div className="flex items-center justify-between pt-4 border-t">
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  disabled={index === 0}
                  onClick={() => checkpointAndGo(index - 1)}
                >
                  Previous
                </Button>
                <Button
                  variant="outline"
                  disabled={index >= questions.length - 1}
                  onClick={() => checkpointAndGo(index + 1)}
                >
                  Next
                </Button>
                <Button variant="ghost" onClick={toggleMarkReview}>
                  {question?.state === "marked_review" ? "Unmark review" : "Mark for review"}
                </Button>
              </div>
              {activeSection?.is_final ? (
                <Button onClick={() => setConfirmOpen(true)}>Submit and End Test</Button>
              ) : (
                <Button onClick={submitSection}>Submit section →</Button>
              )}
            </div>
          </CardContent>
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Questions</CardTitle>
            </CardHeader>
            <CardContent>
              <ProgressPalette
                questions={questions}
                currentIndex={index}
                onJump={(i) => checkpointAndGo(i)}
              />
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Sections</CardTitle>
            </CardHeader>
            <CardContent className="space-y-1 text-sm">
              {state.sections.map((section) => (
                <div key={section.section_id} className="flex justify-between">
                  <span>{section.name}</span>
                  <Badge
                    variant={
                      section.status === "active"
                        ? "default"
                        : section.status === "locked"
                          ? "outline"
                          : "secondary"
                    }
                  >
                    {section.status}
                  </Badge>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      </div>

      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Submit and end test?</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            This is final — you will not be able to return to any section after
            submitting.
          </p>
          <div className="flex gap-2 justify-end">
            <Button variant="outline" onClick={() => setConfirmOpen(false)}>
              Keep working
            </Button>
            <Button onClick={submitExam}>Submit and End Test</Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Full-screen guard — blocking modal shown whenever full screen is left */}
      <Dialog open={fullscreenExited} onOpenChange={() => {}}>
        <DialogContent showCloseButton={false} className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-destructive" />
              You left full screen
            </DialogTitle>
          </DialogHeader>
          <p className="rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
            Warning: leaving full-screen mode is a proctoring violation and has been
            recorded as a red flag on your attempt. Repeated violations may invalidate
            your assessment.
          </p>
          <p className="text-sm text-muted-foreground">
            You must return to full screen to continue the exam. Your timer keeps
            running while this message is shown.
          </p>
          <div className="flex justify-end">
            <Button onClick={reenterFullscreen} disabled={reentering}>
              {reentering ? "Returning…" : "Return to full screen"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </main>
  );
}
