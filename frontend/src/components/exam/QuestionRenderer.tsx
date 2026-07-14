"use client";

import dynamic from "next/dynamic";
import { useState } from "react";
import { toast } from "sonner";
import { api, errorText } from "@/lib/api";
import type { CaseResultOut, CodeRunOut, ExamQuestion } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { CheckCircle2, Play, Send, XCircle } from "lucide-react";

const MonacoEditor = dynamic(() => import("@monaco-editor/react"), { ssr: false });

const MONACO_LANGUAGE: Record<string, string> = {
  javascript: "javascript",
  python: "python",
  java: "java",
  cpp: "cpp",
  c: "c",
};

function CaseResults({ results }: { results: CaseResultOut[] }) {
  return (
    <div className="space-y-2">
      {results.map((result) => (
        <div
          key={`${result.case_id}-${result.hidden}`}
          className="rounded-md border p-2 text-xs space-y-1"
        >
          <div className="flex items-center gap-2">
            {result.passed ? (
              <CheckCircle2 className="h-4 w-4 text-foreground" />
            ) : (
              <XCircle className="h-4 w-4 text-destructive" />
            )}
            <span className="font-medium">
              {result.hidden ? "Hidden case" : `Case ${result.case_id}`}
            </span>
            <Badge variant="outline">{result.status}</Badge>
            <span className="text-muted-foreground">
              {result.time_ms} ms · {Math.round(result.memory_kb / 1024)} MB
            </span>
          </div>
          {!result.hidden && result.stdout && (
            <pre className="rounded bg-muted p-1 overflow-x-auto">out: {result.stdout}</pre>
          )}
          {result.stderr && (
            <pre className="rounded bg-destructive/10 p-1 overflow-x-auto text-destructive">
              {result.stderr}
            </pre>
          )}
        </div>
      ))}
    </div>
  );
}

function CodingAnswer({
  question,
  answer,
  onChange,
}: {
  question: ExamQuestion;
  answer: Record<string, unknown>;
  onChange: (payload: Record<string, unknown>) => void;
}) {
  const allowed = question.config.allowed_languages ?? ["python"];
  const [language, setLanguage] = useState<string>(
    (answer.language as string) ?? allowed[0]
  );
  const [code, setCode] = useState<string>(
    (answer.code as string) ??
      question.config.starter_code?.[allowed[0]] ??
      ""
  );
  const [runResult, setRunResult] = useState<CodeRunOut | null>(null);
  const [busy, setBusy] = useState<"run" | "submit" | null>(null);

  function switchLanguage(next: string) {
    setLanguage(next);
    if (!code.trim() || code === question.config.starter_code?.[language]) {
      setCode(question.config.starter_code?.[next] ?? "");
    }
    onChange({ language: next, code });
  }

  async function execute(kind: "run" | "submit") {
    setBusy(kind);
    try {
      const data = await api<CodeRunOut>(
        `/exam/questions/${question.session_question_id}/code/${kind}`,
        { token: "candidate", body: { language, source_code: code } }
      );
      setRunResult(data);
      if (kind === "submit") {
        toast.success(
          `Submitted: ${data.passed_count}/${data.total_count} test cases passed`
        );
      }
      onChange({ language, code });
    } catch (error) {
      toast.error(errorText(error));
    } finally {
      setBusy(null);
    }
  }

  const visibleCases = question.config.test_cases ?? [];

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <Select value={language} onValueChange={(v) => v && switchLanguage(v)}>
          <SelectTrigger className="w-40">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {allowed.map((lang) => (
              <SelectItem key={lang} value={lang}>
                {lang}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <div className="flex gap-2">
          <Button
            size="sm"
            variant="outline"
            className="gap-1"
            disabled={busy !== null}
            onClick={() => execute("run")}
          >
            <Play className="h-3.5 w-3.5" /> {busy === "run" ? "Running…" : "Run"}
          </Button>
          <Button
            size="sm"
            className="gap-1"
            disabled={busy !== null}
            onClick={() => execute("submit")}
          >
            <Send className="h-3.5 w-3.5" /> {busy === "submit" ? "Submitting…" : "Submit code"}
          </Button>
        </div>
      </div>
      <div className="rounded-md border overflow-hidden">
        <MonacoEditor
          height="320px"
          language={MONACO_LANGUAGE[language] ?? "plaintext"}
          value={code}
          theme="vs-dark"
          onChange={(value) => {
            setCode(value ?? "");
            onChange({ language, code: value ?? "" });
          }}
          options={{ minimap: { enabled: false }, fontSize: 14, contextmenu: false }}
        />
      </div>
      {visibleCases.length > 0 && (
        <div className="text-xs text-muted-foreground">
          Sample cases:{" "}
          {visibleCases.map((c) => `[in: ${c.input ?? ""} → ${c.expected_output ?? ""}]`).join(" ")}
        </div>
      )}
      {runResult && <CaseResults results={runResult.results} />}
    </div>
  );
}

export function QuestionRenderer({
  question,
  answer,
  onChange,
}: {
  question: ExamQuestion;
  answer: Record<string, unknown>;
  onChange: (payload: Record<string, unknown>) => void;
}) {
  if (question.qtype === "mcq") {
    const selected = (answer.selected_option_ids as string[]) ?? [];
    const multi = question.answer_type === "multi_choice";
    return (
      <div className="space-y-2">
        {(question.config.options ?? []).map((option) => {
          const checked = selected.includes(option.id);
          return (
            <label
              key={option.id}
              className="flex items-center gap-3 rounded-md border p-3 text-sm cursor-pointer hover:bg-muted has-[:checked]:border-primary has-[:checked]:bg-primary/5"
            >
              <input
                type={multi ? "checkbox" : "radio"}
                name={question.session_question_id}
                checked={checked}
                onChange={() => {
                  const next = multi
                    ? checked
                      ? selected.filter((id) => id !== option.id)
                      : [...selected, option.id]
                    : [option.id];
                  onChange({ selected_option_ids: next });
                }}
              />
              {option.text}
            </label>
          );
        })}
      </div>
    );
  }

  if (question.qtype === "text") {
    return (
      <Textarea
        rows={8}
        placeholder="Type your answer…"
        value={(answer.text as string) ?? ""}
        onChange={(e) => onChange({ text: e.target.value })}
      />
    );
  }

  return <CodingAnswer question={question} answer={answer} onChange={onChange} />;
}
