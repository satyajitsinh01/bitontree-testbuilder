"use client";

import { use, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, errorText } from "@/lib/api";
import type { ReportOut } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { Sparkles } from "lucide-react";

interface EvaluationOut {
  id: string;
  method: string;
  auto_score: number | null;
  ai_score: number | null;
  ai_rationale: string | null;
  ai_confidence: number | null;
  final_score: number;
  max_score: number;
  overridden_by: string | null;
  override_reason: string | null;
}

interface AnswerItem {
  session_question_id: string;
  qtype: string;
  title: string;
  answer: Record<string, unknown> | null;
  checkpoints: { kind: string; created_at: string }[];
  code_history: {
    id: string;
    kind: string;
    language: string;
    status: string;
    score: number | null;
    created_at: string;
  }[];
  evaluation: EvaluationOut | null;
}

function OverrideDialog({
  evaluation,
  onDone,
}: {
  evaluation: EvaluationOut;
  onDone: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [score, setScore] = useState(evaluation.final_score);
  const [reason, setReason] = useState("");

  const override = useMutation({
    mutationFn: () =>
      api(`/evaluations/${evaluation.id}`, {
        token: "admin",
        method: "PATCH",
        body: { final_score: score, override_reason: reason },
      }),
    onSuccess: () => {
      toast.success("Score overridden (audit logged)");
      setOpen(false);
      onDone();
    },
    onError: (error) => toast.error(errorText(error)),
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button size="sm" variant="outline" />}>
        Override
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Override score</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label>
              Final score (max {evaluation.max_score})
            </Label>
            <Input
              type="number"
              min={0}
              max={evaluation.max_score}
              step={0.5}
              value={score}
              onChange={(e) => setScore(Number(e.target.value))}
            />
          </div>
          <div className="space-y-2">
            <Label>Reason (required, audit-logged)</Label>
            <Textarea value={reason} onChange={(e) => setReason(e.target.value)} />
          </div>
          <Button
            className="w-full"
            onClick={() => override.mutate()}
            disabled={reason.trim().length < 3 || override.isPending}
          >
            Apply override
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

const SEVERITY_VARIANT: Record<string, "destructive" | "secondary" | "outline"> = {
  red_flag: "destructive",
  warning: "secondary",
  info: "outline",
};

export default function SessionReportPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const queryClient = useQueryClient();

  const { data: report } = useQuery({
    queryKey: ["report", id],
    queryFn: () => api<ReportOut>(`/sessions/${id}/report`, { token: "admin" }),
  });
  const { data: answers } = useQuery({
    queryKey: ["answers", id],
    queryFn: () =>
      api<{ items: AnswerItem[] }>(`/sessions/${id}/answers`, { token: "admin" }),
  });

  const finalize = useMutation({
    mutationFn: () =>
      api(`/sessions/${id}/report/finalize`, {
        token: "admin",
        method: "POST",
        body: {},
      }),
    onSuccess: () => {
      toast.success("Report finalized");
      queryClient.invalidateQueries({ queryKey: ["report", id] });
    },
    onError: (error) => toast.error(errorText(error)),
  });

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["report", id] });
    queryClient.invalidateQueries({ queryKey: ["answers", id] });
  };

  if (!report) return <p className="text-muted-foreground">Loading report…</p>;

  return (
    <div className="space-y-6 max-w-5xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            {report.candidate.full_name}
          </h1>
          <p className="text-sm text-muted-foreground">
            {report.candidate.email} · {report.assessment.title}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Badge variant={report.status === "finalized" ? "default" : "secondary"}>
            {report.status}
          </Badge>
          {report.status !== "finalized" && (
            <Button onClick={() => finalize.mutate()} disabled={finalize.isPending}>
              Finalize report
            </Button>
          )}
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-muted-foreground">Overall score</CardTitle>
          </CardHeader>
          <CardContent className="text-3xl font-bold">
            {report.overall_score}
            <span className="text-base font-normal text-muted-foreground">
              {" "}
              / {report.overall_max}
            </span>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-muted-foreground">Integrity</CardTitle>
          </CardHeader>
          <CardContent className="space-x-2">
            <Badge variant="destructive">{report.red_flag_count} red flags</Badge>
            <Badge variant="secondary">{report.warning_count} warnings</Badge>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-muted-foreground">Session</CardTitle>
          </CardHeader>
          <CardContent className="text-sm">
            <p>{report.session.status}</p>
            <p className="text-muted-foreground">
              {report.session.submitted_at
                ? new Date(report.session.submitted_at + "Z").toLocaleString()
                : "—"}
            </p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Section scores</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Section</TableHead>
                <TableHead>Score</TableHead>
                <TableHead>Weightage</TableHead>
                <TableHead>Time spent</TableHead>
                <TableHead>Attempted</TableHead>
                <TableHead>Correct / Wrong</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {report.section_scores.map((section) => (
                <TableRow key={section.section_id}>
                  <TableCell className="font-medium">{section.name}</TableCell>
                  <TableCell>
                    {section.score} / {section.max}
                  </TableCell>
                  <TableCell>{section.weightage_pct}%</TableCell>
                  <TableCell>{Math.round(section.time_spent_sec / 60)} min</TableCell>
                  <TableCell>
                    {section.attempted} ({section.unattempted} skipped)
                  </TableCell>
                  <TableCell>
                    {section.correct} / {section.wrong}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {report.ai_observations && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Sparkles className="h-4 w-4" /> AI observations
            </CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            {report.ai_observations}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Answers & evaluations</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {answers?.items.map((item) => (
            <div key={item.session_question_id} className="rounded-lg border p-4 space-y-2">
              <div className="flex items-center justify-between">
                <p className="font-medium">
                  <Badge variant="outline" className="mr-2">
                    {item.qtype}
                  </Badge>
                  {item.title}
                </p>
                {item.evaluation && (
                  <div className="flex items-center gap-3">
                    <span className="text-sm font-medium">
                      {item.evaluation.final_score} / {item.evaluation.max_score}
                    </span>
                    {report.status !== "finalized" && (
                      <OverrideDialog evaluation={item.evaluation} onDone={refresh} />
                    )}
                  </div>
                )}
              </div>
              {item.evaluation?.ai_rationale && (
                <p className="text-xs text-muted-foreground">
                  AI ({Math.round((item.evaluation.ai_confidence ?? 0) * 100)}% confidence):{" "}
                  {item.evaluation.ai_rationale}
                </p>
              )}
              {item.evaluation?.override_reason && (
                <p className="text-xs text-amber-700">
                  Overridden: {item.evaluation.override_reason}
                </p>
              )}
              {item.answer && (
                <pre className="rounded bg-muted p-2 text-xs overflow-x-auto max-h-40">
                  {JSON.stringify(item.answer, null, 2)}
                </pre>
              )}
              {item.code_history.length > 0 && (
                <p className="text-xs text-muted-foreground">
                  Code history:{" "}
                  {item.code_history
                    .map((c) => `${c.kind}(${c.language}, ${c.status}${c.score != null ? `, ${c.score}` : ""})`)
                    .join(" → ")}
                </p>
              )}
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Proctoring timeline</CardTitle>
        </CardHeader>
        <CardContent>
          {report.proctoring_timeline.length === 0 ? (
            <p className="text-sm text-muted-foreground">No proctoring events recorded.</p>
          ) : (
            <div className="space-y-2">
              {report.proctoring_timeline.map((event, index) => (
                <div key={index} className="flex items-center gap-3 text-sm">
                  <span className="text-xs text-muted-foreground w-40 shrink-0">
                    {new Date(event.occurred_at + "Z").toLocaleTimeString()}
                  </span>
                  <Badge variant={SEVERITY_VARIANT[event.severity] ?? "outline"}>
                    {event.severity}
                  </Badge>
                  <span>{event.kind.replaceAll("_", " ")}</span>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
