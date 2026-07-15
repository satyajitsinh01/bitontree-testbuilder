"use client";

import { useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, errorText, getToken } from "@/lib/api";
import { Button } from "@/components/ui/button";
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { FileJson, Plus, Sparkles, Trash2 } from "lucide-react";

const DIFFICULTIES = ["easy", "medium", "hard"] as const;
const CODING_LANGUAGES = ["python", "javascript", "java", "cpp"] as const;

const DEFAULT_STARTER: Record<string, string> = {
  python: "def solve():\n    # write your logic here\n    pass\n",
  javascript: "function solve() {\n  // write your logic here\n}\n",
  java:
    "class Solution {\n    public static void solve() {\n        // write your logic here\n    }\n}\n",
  cpp: "#include <bits/stdc++.h>\nusing namespace std;\n\nvoid solve() {\n    // write your logic here\n}\n",
};

function DifficultySelect({
  value,
  onChange,
}: {
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <Select value={value} onValueChange={(v) => v && onChange(v)}>
      <SelectTrigger>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {DIFFICULTIES.map((d) => (
          <SelectItem key={d} value={d}>
            {d[0].toUpperCase() + d.slice(1)}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

interface TestCaseRow {
  input: string;
  expected_output: string;
  is_hidden: boolean;
  weight: number;
}

export function NewQuestionDialog({ onDone }: { onDone: () => void }) {
  const [open, setOpen] = useState(false);
  const [qtype, setQtype] = useState<"mcq" | "text" | "coding">("mcq");
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [difficulty, setDifficulty] = useState("medium");
  // MCQ: dynamic option list, single or multiple correct
  const [options, setOptions] = useState<string[]>(["", ""]);
  const [correct, setCorrect] = useState<Set<number>>(new Set([0]));
  const [multiCorrect, setMultiCorrect] = useState(false);
  // text
  const [rubric, setRubric] = useState("");
  // coding: boilerplate per language + test cases
  const [languages, setLanguages] = useState<Set<string>>(new Set(["python"]));
  const [starterCode, setStarterCode] = useState<Record<string, string>>({
    python: DEFAULT_STARTER.python,
  });
  const [cases, setCases] = useState<TestCaseRow[]>([
    { input: "", expected_output: "", is_hidden: false, weight: 1 },
  ]);

  function toggleLanguage(lang: string) {
    const next = new Set(languages);
    if (next.has(lang)) {
      if (next.size === 1) return; // keep at least one
      next.delete(lang);
    } else {
      next.add(lang);
      if (!starterCode[lang]) {
        setStarterCode((prev) => ({ ...prev, [lang]: DEFAULT_STARTER[lang] ?? "" }));
      }
    }
    setLanguages(next);
  }

  function toggleCorrect(index: number) {
    if (multiCorrect) {
      const next = new Set(correct);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      setCorrect(next);
    } else {
      setCorrect(new Set([index]));
    }
  }

  function removeOption(index: number) {
    if (options.length <= 2) return;
    setOptions(options.filter((_, i) => i !== index));
    const next = new Set<number>();
    for (const c of correct) {
      if (c === index) continue;
      next.add(c > index ? c - 1 : c);
    }
    if (next.size === 0) next.add(0);
    setCorrect(next);
  }

  const filledOptions = options.filter((o) => o.trim());
  const mcqValid =
    filledOptions.length >= 2 &&
    correct.size >= 1 &&
    [...correct].every((i) => options[i]?.trim());
  const codingValid =
    cases.length >= 1 && cases.every((c) => c.expected_output.trim() !== "");
  const formValid =
    title.trim().length >= 3 &&
    (qtype === "mcq" ? mcqValid : qtype === "coding" ? codingValid : rubric.trim() !== "");

  const create = useMutation({
    mutationFn: () => {
      let config: Record<string, unknown> = {};
      let answerType = "single_choice";
      if (qtype === "mcq") {
        const opts = options
          .map((text, i) => ({ id: `o${i}`, text: text.trim(), index: i }))
          .filter((o) => o.text);
        config = {
          options: opts.map(({ id, text }) => ({ id, text })),
          correct_option_ids: [...correct]
            .filter((i) => options[i]?.trim())
            .map((i) => `o${i}`),
        };
        answerType = multiCorrect ? "multi_choice" : "single_choice";
      } else if (qtype === "text") {
        config = { rubric };
        answerType = "long_text";
      } else {
        config = {
          allowed_languages: [...languages],
          starter_code: Object.fromEntries(
            [...languages].map((l) => [l, starterCode[l] ?? ""])
          ),
          show_case_results: "visible_only",
          test_cases: cases.map((c, i) => ({
            id: `t${i + 1}`,
            input: c.input,
            expected_output: c.expected_output,
            is_hidden: c.is_hidden,
            weight: c.weight || 1,
          })),
        };
        answerType = "code";
      }
      return api("/questions", {
        token: "admin",
        body: { qtype, title, body, difficulty, config, answer_type: answerType },
      });
    },
    onSuccess: () => {
      toast.success("Question created");
      setOpen(false);
      setTitle("");
      setBody("");
      setOptions(["", ""]);
      setCorrect(new Set([0]));
      onDone();
    },
    onError: (error) => toast.error(errorText(error)),
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button variant="outline" className="gap-2" />}>
        <Plus className="h-4 w-4" /> New question
      </DialogTrigger>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>New question</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label>Type</Label>
              <Select value={qtype} onValueChange={(v) => v && setQtype(v as typeof qtype)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="mcq">MCQ</SelectItem>
                  <SelectItem value="text">Written answer</SelectItem>
                  <SelectItem value="coding">Coding</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Difficulty</Label>
              <DifficultySelect value={difficulty} onChange={setDifficulty} />
            </div>
          </div>
          <div className="space-y-2">
            <Label>Title</Label>
            <Input value={title} onChange={(e) => setTitle(e.target.value)} />
          </div>
          <div className="space-y-2">
            <Label>Question body</Label>
            <Textarea value={body} onChange={(e) => setBody(e.target.value)} rows={3} />
          </div>

          {qtype === "mcq" && (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <Label>Options — mark the correct one{multiCorrect ? "s" : ""}</Label>
                <label className="flex items-center gap-2 text-xs text-muted-foreground">
                  <input
                    type="checkbox"
                    checked={multiCorrect}
                    onChange={(e) => {
                      setMultiCorrect(e.target.checked);
                      if (!e.target.checked && correct.size > 1) {
                        setCorrect(new Set([[...correct][0]]));
                      }
                    }}
                  />
                  Multiple correct answers
                </label>
              </div>
              {options.map((opt, i) => (
                <div key={i} className="flex items-center gap-2">
                  <input
                    type={multiCorrect ? "checkbox" : "radio"}
                    name="correct-option"
                    checked={correct.has(i)}
                    onChange={() => toggleCorrect(i)}
                  />
                  <Input
                    value={opt}
                    placeholder={`Option ${i + 1}`}
                    onChange={(e) =>
                      setOptions(options.map((o, j) => (j === i ? e.target.value : o)))
                    }
                  />
                  <Button
                    size="icon-sm"
                    variant="ghost"
                    disabled={options.length <= 2}
                    onClick={() => removeOption(i)}
                    aria-label={`Remove option ${i + 1}`}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              ))}
              <Button
                size="sm"
                variant="outline"
                className="gap-1"
                disabled={options.length >= 10}
                onClick={() => setOptions([...options, ""])}
              >
                <Plus className="h-3.5 w-3.5" /> Add option
              </Button>
            </div>
          )}

          {qtype === "text" && (
            <div className="space-y-2">
              <Label>Evaluation rubric</Label>
              <Textarea
                value={rubric}
                onChange={(e) => setRubric(e.target.value)}
                placeholder="What a good answer must cover — used by the AI evaluator."
              />
            </div>
          )}

          {qtype === "coding" && (
            <div className="space-y-4">
              <div className="space-y-2">
                <Label>Allowed languages</Label>
                <div className="flex flex-wrap gap-3">
                  {CODING_LANGUAGES.map((lang) => (
                    <label key={lang} className="flex items-center gap-1.5 text-sm">
                      <input
                        type="checkbox"
                        checked={languages.has(lang)}
                        onChange={() => toggleLanguage(lang)}
                      />
                      {lang}
                    </label>
                  ))}
                </div>
              </div>
              {[...languages].map((lang) => (
                <div key={lang} className="space-y-1.5">
                  <Label className="font-mono text-xs">
                    Boilerplate ({lang}) — the function/class the candidate completes
                  </Label>
                  <Textarea
                    className="font-mono text-xs"
                    rows={5}
                    value={starterCode[lang] ?? ""}
                    onChange={(e) =>
                      setStarterCode((prev) => ({ ...prev, [lang]: e.target.value }))
                    }
                  />
                </div>
              ))}
              <div className="space-y-2">
                <Label>Test cases (hidden ones are used only for scoring)</Label>
                {cases.map((c, i) => (
                  <div key={i} className="grid grid-cols-[1fr_1fr_auto_auto_auto] gap-2 items-center">
                    <Input
                      placeholder="stdin input"
                      value={c.input}
                      onChange={(e) =>
                        setCases(cases.map((x, j) => (j === i ? { ...x, input: e.target.value } : x)))
                      }
                    />
                    <Input
                      placeholder="expected output"
                      value={c.expected_output}
                      onChange={(e) =>
                        setCases(
                          cases.map((x, j) =>
                            j === i ? { ...x, expected_output: e.target.value } : x
                          )
                        )
                      }
                    />
                    <label className="flex items-center gap-1 text-xs">
                      <input
                        type="checkbox"
                        checked={c.is_hidden}
                        onChange={(e) =>
                          setCases(
                            cases.map((x, j) =>
                              j === i ? { ...x, is_hidden: e.target.checked } : x
                            )
                          )
                        }
                      />
                      hidden
                    </label>
                    <Input
                      className="w-16"
                      type="number"
                      min={1}
                      title="weight"
                      value={c.weight}
                      onChange={(e) =>
                        setCases(
                          cases.map((x, j) =>
                            j === i ? { ...x, weight: Number(e.target.value) } : x
                          )
                        )
                      }
                    />
                    <Button
                      size="icon-sm"
                      variant="ghost"
                      disabled={cases.length <= 1}
                      onClick={() => setCases(cases.filter((_, j) => j !== i))}
                      aria-label={`Remove case ${i + 1}`}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                ))}
                <Button
                  size="sm"
                  variant="outline"
                  className="gap-1"
                  onClick={() =>
                    setCases([...cases, { input: "", expected_output: "", is_hidden: true, weight: 1 }])
                  }
                >
                  <Plus className="h-3.5 w-3.5" /> Add test case
                </Button>
              </div>
            </div>
          )}

          <Button
            className="w-full"
            onClick={() => create.mutate()}
            disabled={!formValid || create.isPending}
          >
            {create.isPending ? "Creating…" : "Create question"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export function AiGenerateDialog({ onDone }: { onDone: () => void }) {
  const [open, setOpen] = useState(false);
  const [prompt, setPrompt] = useState("");
  const [topic, setTopic] = useState("");
  const [qtype, setQtype] = useState("mcq");
  const [difficulty, setDifficulty] = useState("medium");
  const [count, setCount] = useState(5);

  const generate = useMutation({
    mutationFn: () =>
      api<{ status: string; question_ids: string[]; skipped_duplicates: number }>(
        "/questions/ai-generate",
        {
          token: "admin",
          body: { prompt, qtype, count, topic: topic || "general", difficulty },
        }
      ),
    onSuccess: (data) => {
      if (data.status === "completed") {
        const skipped = data.skipped_duplicates
          ? ` (${data.skipped_duplicates} skipped as duplicates of existing questions)`
          : "";
        toast.success(
          `${data.question_ids.length} draft questions generated${skipped} — review and approve them.`
        );
      } else {
        toast.error("Generation failed — check AI configuration.");
      }
      setOpen(false);
      onDone();
    },
    onError: (error) => toast.error(errorText(error)),
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button className="gap-2" />}>
        <Sparkles className="h-4 w-4" /> Generate with AI
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>AI question generation</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label>Prompt</Label>
            <Textarea
              value={prompt}
              placeholder="e.g. Intermediate Python questions on list comprehensions"
              onChange={(e) => setPrompt(e.target.value)}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label>Topic</Label>
              <Input value={topic} onChange={(e) => setTopic(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label>Difficulty</Label>
              <DifficultySelect value={difficulty} onChange={setDifficulty} />
            </div>
            <div className="space-y-2">
              <Label>Type</Label>
              <Select value={qtype} onValueChange={(v) => v && setQtype(v)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="mcq">MCQ</SelectItem>
                  <SelectItem value="text">Written</SelectItem>
                  <SelectItem value="coding">Coding</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Count</Label>
              <Input
                type="number"
                min={1}
                max={30}
                value={count}
                onChange={(e) => setCount(Number(e.target.value))}
              />
            </div>
          </div>
          <p className="text-xs text-muted-foreground">
            Generated questions land as drafts and must be approved before use.
            Near-duplicates of existing bank questions are skipped automatically.
          </p>
          <Button
            className="w-full"
            onClick={() => generate.mutate()}
            disabled={prompt.trim().length < 3 || generate.isPending}
          >
            {generate.isPending ? "Generating…" : "Generate drafts"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

interface ImportResult {
  imported: number;
  failed: number;
  errors: { index: number; title?: string; error: string }[];
}

export function ImportQuestionsDialog({ onDone }: { onDone: () => void }) {
  // The file input lives OUTSIDE any dialog: opening the OS file picker blurs the
  // window, which would close a Base UI dialog and unmount an input rendered
  // inside it before onChange fires. Results are shown in a dialog afterwards.
  const fileRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [resultOpen, setResultOpen] = useState(false);

  async function downloadTemplate() {
    try {
      const template = await api<unknown>("/questions/import-template", { token: "admin" });
      const blob = new Blob([JSON.stringify(template, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "questions-template.json";
      link.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      toast.error(errorText(error));
    }
  }

  async function upload(file: File) {
    setBusy(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
      const response = await fetch(`${base}/api/v1/questions/import`, {
        method: "POST",
        headers: { Authorization: `Bearer ${getToken("admin")}` },
        body: form,
      });
      const payload = await response.json();
      if (!response.ok) {
        const details = payload.error?.details;
        throw new Error(
          Array.isArray(details) ? details.join("; ") : payload.error?.code ?? "import failed"
        );
      }
      setResult(payload.data as ImportResult);
      setResultOpen(true);
      if (payload.data.imported > 0) {
        toast.success(
          `${payload.data.imported} question(s) imported as drafts — review and approve them.`
        );
      } else {
        toast.error("No questions imported — check the file format.");
      }
      onDone();
    } catch (error) {
      toast.error(errorText(error));
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  return (
    <>
      <input
        ref={fileRef}
        type="file"
        accept=".json,application/json"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) upload(file);
        }}
      />
      <Button variant="ghost" size="sm" onClick={downloadTemplate}>
        Template
      </Button>
      <Button
        variant="outline"
        className="gap-2"
        disabled={busy}
        onClick={() => fileRef.current?.click()}
      >
        <FileJson className="h-4 w-4" /> {busy ? "Importing…" : "Import JSON"}
      </Button>

      <Dialog open={resultOpen} onOpenChange={setResultOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Import results</DialogTitle>
          </DialogHeader>
          {result && (
            <div className="space-y-2 text-sm">
              <p>
                Imported <strong>{result.imported}</strong> as drafts · Failed{" "}
                <strong>{result.failed}</strong>
              </p>
              {result.imported > 0 && (
                <p className="text-xs text-muted-foreground">
                  Filter by “Drafts” and approve them to make them usable.
                </p>
              )}
              {result.errors.length > 0 && (
                <ul className="space-y-1 rounded-lg border border-destructive/30 bg-destructive/5 p-2 text-xs text-destructive max-h-56 overflow-y-auto">
                  {result.errors.map((e) => (
                    <li key={e.index}>
                      #{e.index + 1} {e.title ? `(${e.title}) ` : ""}— {e.error}
                    </li>
                  ))}
                </ul>
              )}
              <Button className="w-full" onClick={() => setResultOpen(false)}>
                Done
              </Button>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
