"use client";

import dynamic from "next/dynamic";
import type { editor } from "monaco-editor";
import { useMemo, useState } from "react";
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
import { Markdown } from "@/components/ui/markdown";
import { CheckCircle2, Play, Send, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";

const MonacoEditor = dynamic(() => import("@monaco-editor/react"), { ssr: false });

const MONACO_LANGUAGE: Record<string, string> = {
  javascript: "javascript",
  python: "python",
  java: "java",
  cpp: "cpp",
  c: "c",
};
const LANGUAGE_LABEL: Record<string, string> = {
  python: "Python 3",
  javascript: "JavaScript",
  java: "Java",
  cpp: "C++",
  c: "C",
};
const DIFFICULTY_LABEL: Record<string, string> = {
  easy: "Easy",
  medium: "Medium",
  hard: "Hard",
};

/** Blocks every paste path in Monaco: Ctrl/Cmd+V keybindings, the DOM paste
 * event (capture phase), and drag & drop. Candidates must type manually. */
function installPasteGuard(
  ed: editor.IStandaloneCodeEditor,
  monaco: typeof import("monaco-editor"),
  onBlocked: () => void
) {
  const swallow = () => onBlocked();
  ed.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyV, swallow);
  ed.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyMod.Shift | monaco.KeyCode.KeyV, swallow);
  const dom = ed.getDomNode();
  if (dom) {
    const block = (e: Event) => {
      e.preventDefault();
      e.stopPropagation();
      onBlocked();
    };
    dom.addEventListener("paste", block, true);
    dom.addEventListener("drop", block, true);
    dom.addEventListener("dragover", (e) => e.preventDefault(), true);
  }
  ed.updateOptions({ dragAndDrop: false, contextmenu: false });
}

function ProblemPanel({ question }: { question: ExamQuestion }) {
  const c = question.config;
  const difficulty = question.difficulty ?? "medium";
  return (
    <div className="h-full overflow-y-auto p-5 space-y-4">
      <div className="space-y-2">
        <h1 className="text-xl font-semibold tracking-tight">{question.title}</h1>
        <div className="flex flex-wrap items-center gap-2">
          <Badge
            variant="outline"
            className={cn(
              difficulty === "easy" && "border-foreground/30",
              difficulty === "hard" && "border-destructive/40 text-destructive"
            )}
          >
            {DIFFICULTY_LABEL[difficulty] ?? difficulty}
          </Badge>
          {(question.tags ?? c.tags ?? []).map((t) => (
            <Badge key={t} variant="secondary">
              {t}
            </Badge>
          ))}
          <span className="text-xs text-muted-foreground">{question.points} pts</span>
        </div>
      </div>

      {c.description && <Markdown>{c.description}</Markdown>}
      {!c.description && question.body && <Markdown>{question.body}</Markdown>}

      {c.input_format && (
        <section>
          <h2 className="mb-1 text-sm font-semibold">Input</h2>
          <Markdown>{c.input_format}</Markdown>
        </section>
      )}
      {c.output_format && (
        <section>
          <h2 className="mb-1 text-sm font-semibold">Output</h2>
          <Markdown>{c.output_format}</Markdown>
        </section>
      )}

      {(c.examples ?? []).length > 0 && (
        <section className="space-y-3">
          {c.examples!.map((ex, i) => (
            <div key={i} className="rounded-lg border bg-muted/30 p-3">
              <p className="mb-1 text-xs font-semibold text-muted-foreground">
                Example {i + 1}
              </p>
              <div className="space-y-1 font-mono text-xs">
                <p>
                  <span className="text-muted-foreground">Input: </span>
                  {ex.input}
                </p>
                <p>
                  <span className="text-muted-foreground">Output: </span>
                  {ex.output}
                </p>
              </div>
              {ex.explanation && (
                <div className="mt-1.5 text-xs">
                  <Markdown>{`**Explanation:** ${ex.explanation}`}</Markdown>
                </div>
              )}
            </div>
          ))}
        </section>
      )}

      {c.constraints && (
        <section>
          <h2 className="mb-1 text-sm font-semibold">Constraints</h2>
          <Markdown>{c.constraints}</Markdown>
        </section>
      )}
      {c.notes && (
        <section>
          <h2 className="mb-1 text-sm font-semibold">Notes</h2>
          <Markdown>{c.notes}</Markdown>
        </section>
      )}
    </div>
  );
}

function ResultView({
  result,
  hiddenCount,
}: {
  result: CodeRunOut;
  hiddenCount: number;
}) {
  const cases = result.results ?? [];
  const custom = cases.filter((r) => r.custom);
  const sample = cases.filter((r) => !r.custom && !r.hidden);
  const hidden = cases.filter((r) => r.hidden);
  const compileErr = cases.find((r) => r.status === "compile_error");
  const runtimeErr = cases.find((r) => r.status === "runtime_error" && r.stderr);
  const total = result.total_count ?? sample.length + hidden.length;
  const passed = result.passed_count ?? cases.filter((r) => !r.custom && r.passed).length;
  const allPass = total > 0 && passed === total;

  return (
    <div className="space-y-3 p-3 text-sm">
      <div className="flex items-center gap-2">
        {allPass ? (
          <CheckCircle2 className="h-5 w-5 text-foreground" />
        ) : (
          <XCircle className="h-5 w-5 text-destructive" />
        )}
        <span className="font-semibold">
          {allPass ? "Accepted" : compileErr ? "Compile Error" : "Wrong Answer"}
        </span>
        <span className="text-muted-foreground">
          {passed}/{total} test cases passed
        </span>
        {result.score != null && (
          <Badge variant="outline" className="ml-auto">
            score {result.score}
          </Badge>
        )}
      </div>

      {compileErr?.stderr && (
        <pre className="overflow-x-auto rounded-md bg-destructive/10 p-2 text-xs text-destructive">
          {compileErr.stderr}
        </pre>
      )}
      {runtimeErr?.stderr && !compileErr && (
        <pre className="overflow-x-auto rounded-md bg-destructive/10 p-2 text-xs text-destructive">
          {runtimeErr.stderr}
        </pre>
      )}

      {sample.map((r) => (
        <CaseCard key={r.case_id} r={r} label={`Case ${r.case_id}`} />
      ))}
      {custom.map((r) => (
        <CaseCard key={r.case_id} r={r} label="Custom input" custom />
      ))}
      {hidden.length > 0 && (
        <p className="text-xs text-muted-foreground">
          {hidden.filter((r) => r.passed).length}/{hidden.length} hidden test cases passed
          (inputs and outputs are not shown).
        </p>
      )}
      {hidden.length === 0 && hiddenCount > 0 && (
        <p className="text-xs text-muted-foreground">
          + {hiddenCount} hidden test cases run on Submit.
        </p>
      )}
    </div>
  );
}

function CaseCard({
  r,
  label,
  custom,
}: {
  r: CaseResultOut;
  label: string;
  custom?: boolean;
}) {
  return (
    <div className="rounded-md border p-2 text-xs space-y-1">
      <div className="flex items-center gap-2">
        {!custom &&
          (r.passed ? (
            <CheckCircle2 className="h-4 w-4 text-foreground" />
          ) : (
            <XCircle className="h-4 w-4 text-destructive" />
          ))}
        <span className="font-medium">{label}</span>
        <Badge variant="outline">{r.status}</Badge>
        <span className="text-muted-foreground">
          {r.time_ms} ms · {Math.round(r.memory_kb / 1024)} MB
        </span>
      </div>
      {r.input_display && (
        <p className="font-mono">
          <span className="text-muted-foreground">Input: </span>
          {r.input_display.replace(/\n/g, ", ")}
        </p>
      )}
      {r.stdout && (
        <p className="font-mono">
          <span className="text-muted-foreground">Output: </span>
          {r.stdout}
        </p>
      )}
      {!custom && r.expected_display && (
        <p className="font-mono">
          <span className="text-muted-foreground">Expected: </span>
          {r.expected_display}
        </p>
      )}
      {r.stderr && (
        <pre className="overflow-x-auto rounded bg-destructive/10 p-1 text-destructive">
          {r.stderr}
        </pre>
      )}
    </div>
  );
}

export function CodingWorkspace({
  question,
  answer,
  onChange,
}: {
  question: ExamQuestion;
  answer: Record<string, unknown>;
  onChange: (payload: Record<string, unknown>) => void;
}) {
  const config = question.config;
  const allowed = useMemo(
    () => config.allowed_languages ?? Object.keys(config.starter_code ?? { python: "" }),
    [config]
  );
  const [language, setLanguage] = useState<string>(
    (answer.language as string) ?? allowed[0]
  );
  const [code, setCode] = useState<string>(
    (answer.code as string) ?? config.starter_code?.[allowed[0]] ?? ""
  );
  const [customInput, setCustomInput] = useState<string>(
    (answer.custom_input as string) ?? ""
  );
  const [tab, setTab] = useState<"testcase" | "result">("testcase");
  const [runResult, setRunResult] = useState<CodeRunOut | null>(null);
  const [busy, setBusy] = useState<"run" | "submit" | null>(null);

  function switchLanguage(next: string) {
    setLanguage(next);
    const starter = config.starter_code?.[next] ?? "";
    // only overwrite if the editor still holds a starter template
    const isTemplate =
      !code.trim() ||
      Object.values(config.starter_code ?? {}).some((s) => s.trim() === code.trim());
    const nextCode = isTemplate ? starter : code;
    setCode(nextCode);
    onChange({ language: next, code: nextCode, custom_input: customInput });
  }

  async function execute(kind: "run" | "submit") {
    setBusy(kind);
    setTab("result");
    try {
      const body: Record<string, unknown> = { language, source_code: code };
      if (kind === "run" && customInput.trim()) body.custom_input = customInput;
      const data = await api<CodeRunOut>(
        `/exam/questions/${question.session_question_id}/code/${kind}`,
        { token: "candidate", body }
      );
      setRunResult(data);
      if (kind === "submit") {
        const ok = data.passed_count === data.total_count;
        (ok ? toast.success : toast.error)(
          `${ok ? "Accepted" : "Wrong Answer"} — ${data.passed_count}/${data.total_count} passed`
        );
      }
      onChange({ language, code, custom_input: customInput });
    } catch (error) {
      toast.error(errorText(error));
    } finally {
      setBusy(null);
    }
  }

  const sampleCases = config.test_cases ?? [];
  const paramCount = config.signature?.params.length ?? 1;

  return (
    <div className="grid gap-3 lg:grid-cols-2 min-h-[70vh]">
      <div className="rounded-lg border bg-background overflow-hidden">
        <ProblemPanel question={question} />
      </div>

      <div className="flex flex-col rounded-lg border bg-background overflow-hidden">
        <div className="flex items-center justify-between gap-2 border-b p-2">
          <Select value={language} onValueChange={(v) => v && switchLanguage(v)}>
            <SelectTrigger className="w-40">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {allowed.map((lang) => (
                <SelectItem key={lang} value={lang}>
                  {LANGUAGE_LABEL[lang] ?? lang}
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
              <Send className="h-3.5 w-3.5" /> {busy === "submit" ? "Submitting…" : "Submit"}
            </Button>
          </div>
        </div>

        <div className="min-h-[300px] flex-1">
          <MonacoEditor
            height="100%"
            language={MONACO_LANGUAGE[language] ?? "plaintext"}
            value={code}
            theme="vs-dark"
            onMount={(ed, monaco) =>
              installPasteGuard(ed, monaco, () =>
                toast.warning("Pasting is disabled — type your solution manually.")
              )
            }
            onChange={(value) => {
              setCode(value ?? "");
              onChange({ language, code: value ?? "", custom_input: customInput });
            }}
            options={{
              minimap: { enabled: false },
              fontSize: 14,
              contextmenu: false,
              dragAndDrop: false,
              scrollBeyondLastLine: false,
              automaticLayout: true,
            }}
          />
        </div>

        <div className="border-t">
          <div className="flex gap-1 border-b px-2 pt-2 text-sm">
            <button
              className={cn(
                "rounded-t px-3 py-1.5 font-medium",
                tab === "testcase" ? "bg-muted" : "text-muted-foreground"
              )}
              onClick={() => setTab("testcase")}
            >
              Testcase
            </button>
            <button
              className={cn(
                "rounded-t px-3 py-1.5 font-medium",
                tab === "result" ? "bg-muted" : "text-muted-foreground"
              )}
              onClick={() => setTab("result")}
            >
              Result
            </button>
          </div>
          <div className="max-h-56 overflow-y-auto">
            {tab === "testcase" ? (
              <div className="space-y-3 p-3 text-xs">
                {sampleCases.length > 0 && (
                  <div className="space-y-1">
                    <p className="font-medium text-muted-foreground">Sample cases</p>
                    {sampleCases.map((tc) => (
                      <div key={tc.id} className="rounded border p-2 font-mono">
                        <p>args: {JSON.stringify(tc.args ?? tc.input)}</p>
                        <p>expected: {JSON.stringify(tc.expected ?? tc.expected_output)}</p>
                      </div>
                    ))}
                  </div>
                )}
                <div className="space-y-1">
                  <p className="font-medium text-muted-foreground">
                    Custom input — one JSON value per line ({paramCount} value
                    {paramCount === 1 ? "" : "s"}), used by Run
                  </p>
                  <textarea
                    className="w-full rounded-md border bg-transparent p-2 font-mono text-xs outline-none focus-visible:border-ring"
                    rows={paramCount + 1}
                    placeholder={"[2,7,11,15]\n9"}
                    value={customInput}
                    onChange={(e) => {
                      setCustomInput(e.target.value);
                      onChange({ language, code, custom_input: e.target.value });
                    }}
                  />
                </div>
              </div>
            ) : runResult ? (
              <ResultView result={runResult} hiddenCount={config.hidden_case_count ?? 0} />
            ) : (
              <p className="p-4 text-sm text-muted-foreground">
                Run or Submit to see results.
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
