"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, errorText } from "@/lib/api";
import type { QuestionOut } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
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
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Markdown } from "@/components/ui/markdown";
import { Eye, Pencil, Plus, Trash2 } from "lucide-react";

const DIFFICULTIES = ["easy", "medium", "hard"] as const;

// ------------------------------------------------------------------ View ----
function ViewQuestionDialog({ question }: { question: QuestionOut }) {
  const v = question.current_version;
  if (!v) return null;
  const c = v.config;
  return (
    <Dialog>
      <DialogTrigger
        render={<Button size="icon" variant="ghost" title="View question" />}
      >
        <Eye className="h-4 w-4" />
      </DialogTrigger>
      <DialogContent className="sm:max-w-2xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{v.title}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3 text-sm">
          <div className="flex flex-wrap gap-2">
            <Badge variant="outline">{v.qtype}</Badge>
            <Badge variant="secondary">{v.difficulty}</Badge>
            <Badge variant="outline">{question.status}</Badge>
            <Badge variant="outline">source: {question.source}</Badge>
            <span className="text-xs text-muted-foreground">version {v.version}</span>
          </div>

          {(c.description || v.body) && <Markdown>{c.description || v.body}</Markdown>}

          {v.qtype === "mcq" && (
            <div className="space-y-1">
              <Label>Options</Label>
              {(c.options ?? []).map((o) => (
                <div
                  key={o.id}
                  className={`flex items-center gap-2 rounded border p-2 ${
                    (c.correct_option_ids ?? []).includes(o.id)
                      ? "border-primary bg-primary/5"
                      : ""
                  }`}
                >
                  {(c.correct_option_ids ?? []).includes(o.id) && (
                    <Badge variant="default">correct</Badge>
                  )}
                  <span>{o.text}</span>
                </div>
              ))}
            </div>
          )}

          {v.qtype === "text" && c.rubric && (
            <div>
              <Label>Rubric</Label>
              <p className="rounded border bg-muted/40 p-2">{c.rubric}</p>
            </div>
          )}

          {v.qtype === "coding" && (
            <div className="space-y-2">
              {c.signature && (
                <p className="font-mono text-xs">
                  {c.signature.return_type} {c.signature.function_name}(
                  {c.signature.params.map((p) => `${p.type} ${p.name}`).join(", ")})
                </p>
              )}
              {c.constraints && (
                <div>
                  <Label>Constraints</Label>
                  <Markdown>{c.constraints}</Markdown>
                </div>
              )}
              <div>
                <Label>Test cases ({(c.test_cases ?? []).length})</Label>
                <div className="space-y-1">
                  {(c.test_cases ?? []).map((tc) => (
                    <div key={tc.id} className="rounded border p-2 font-mono text-xs">
                      <span className="text-muted-foreground">
                        {tc.is_hidden ? "hidden" : "sample"}:{" "}
                      </span>
                      args={JSON.stringify(tc.args ?? tc.input)} → expected=
                      {JSON.stringify(tc.expected ?? tc.expected_output)}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ------------------------------------------------------------------ Edit ----
function EditQuestionDialog({
  question,
  onDone,
}: {
  question: QuestionOut;
  onDone: () => void;
}) {
  const v = question.current_version!;
  const c = v.config;
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState(v.title);
  const [body, setBody] = useState(v.body);
  const [difficulty, setDifficulty] = useState(v.difficulty);
  // MCQ state
  const [options, setOptions] = useState<string[]>(
    v.qtype === "mcq" ? (c.options ?? []).map((o) => o.text) : ["", ""]
  );
  const [correct, setCorrect] = useState<Set<number>>(
    v.qtype === "mcq"
      ? new Set(
          (c.options ?? [])
            .map((o, i) => ((c.correct_option_ids ?? []).includes(o.id) ? i : -1))
            .filter((i) => i >= 0)
        )
      : new Set([0])
  );
  const multiCorrect = v.answer_type === "multi_choice";
  const [rubric, setRubric] = useState(c.rubric ?? "");
  // coding: raw JSON config editor (LeetCode config is rich)
  const [configJson, setConfigJson] = useState(() => JSON.stringify(c, null, 2));
  const [jsonError, setJsonError] = useState<string | null>(null);

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

  const save = useMutation({
    mutationFn: () => {
      let config: Record<string, unknown>;
      if (v.qtype === "mcq") {
        const opts = options
          .map((text, i) => ({ id: `o${i}`, text: text.trim(), i }))
          .filter((o) => o.text);
        config = {
          options: opts.map(({ id, text }) => ({ id, text })),
          correct_option_ids: [...correct]
            .filter((i) => options[i]?.trim())
            .map((i) => `o${i}`),
        };
      } else if (v.qtype === "text") {
        config = { rubric };
      } else {
        config = JSON.parse(configJson);
      }
      return api(`/questions/${question.id}`, {
        token: "admin",
        method: "PUT",
        body: {
          qtype: v.qtype,
          title,
          body,
          difficulty,
          answer_type: v.answer_type,
          category: v.category,
          topic: v.topic,
          skills: v.skills,
          tags: v.tags,
          config,
        },
      });
    },
    onSuccess: () => {
      toast.success("Question updated (new version created)");
      setOpen(false);
      onDone();
    },
    onError: (error) => toast.error(errorText(error)),
  });

  function validateAndSave() {
    if (v.qtype === "coding") {
      try {
        JSON.parse(configJson);
        setJsonError(null);
      } catch (e) {
        setJsonError(e instanceof Error ? e.message : "invalid JSON");
        return;
      }
    }
    save.mutate();
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger
        render={<Button size="icon" variant="ghost" title="Edit question" />}
      >
        <Pencil className="h-4 w-4" />
      </DialogTrigger>
      <DialogContent className="sm:max-w-2xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Edit question</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <p className="rounded-lg border bg-muted/50 px-3 py-2 text-xs text-muted-foreground">
            Saving creates a new version. Questions already frozen inside a started
            assessment keep their original version.
          </p>
          <div className="grid grid-cols-[1fr_auto] gap-4">
            <div className="space-y-2">
              <Label>Title</Label>
              <Input value={title} onChange={(e) => setTitle(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label>Difficulty</Label>
              <Select value={difficulty} onValueChange={(x) => x && setDifficulty(x)}>
                <SelectTrigger className="w-32">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {DIFFICULTIES.map((d) => (
                    <SelectItem key={d} value={d}>
                      {d}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="space-y-2">
            <Label>{v.qtype === "coding" ? "Prompt / short description" : "Body"}</Label>
            <Textarea rows={2} value={body} onChange={(e) => setBody(e.target.value)} />
          </div>

          {v.qtype === "mcq" && (
            <div className="space-y-2">
              <Label>Options — mark the correct one{multiCorrect ? "s" : ""}</Label>
              {options.map((opt, i) => (
                <div key={i} className="flex items-center gap-2">
                  <input
                    type={multiCorrect ? "checkbox" : "radio"}
                    name="edit-correct"
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
                    onClick={() => setOptions(options.filter((_, j) => j !== i))}
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

          {v.qtype === "text" && (
            <div className="space-y-2">
              <Label>Evaluation rubric</Label>
              <Textarea value={rubric} onChange={(e) => setRubric(e.target.value)} />
            </div>
          )}

          {v.qtype === "coding" && (
            <div className="space-y-2">
              <Label>
                Config (JSON) — signature, description, test cases, limits. Starter code
                is regenerated from the signature on save.
              </Label>
              <Textarea
                className="font-mono text-xs"
                rows={16}
                value={configJson}
                onChange={(e) => {
                  setConfigJson(e.target.value);
                  setJsonError(null);
                }}
              />
              {jsonError && <p className="text-xs text-destructive">{jsonError}</p>}
            </div>
          )}

          <Button
            className="w-full"
            onClick={validateAndSave}
            disabled={title.trim().length < 3 || save.isPending}
          >
            {save.isPending ? "Saving…" : "Save changes"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------- Actions ---
export function QuestionRowActions({
  question,
  onDone,
}: {
  question: QuestionOut;
  onDone: () => void;
}) {
  const remove = useMutation({
    mutationFn: () => api(`/questions/${question.id}`, { token: "admin", method: "DELETE" }),
    onSuccess: () => {
      toast.success("Question deleted");
      onDone();
    },
    onError: (error) => toast.error(errorText(error)),
  });

  return (
    <div className="flex items-center gap-0.5">
      <ViewQuestionDialog question={question} />
      <EditQuestionDialog question={question} onDone={onDone} />
      <ConfirmDialog
        trigger={
          <Button size="icon" variant="ghost" title="Delete question">
            <Trash2 className="h-4 w-4" />
          </Button>
        }
        title="Delete this question?"
        description={
          <>
            <strong>{question.current_version?.title}</strong> will be removed from the
            bank.
          </>
        }
        warning="This cannot be undone. A question already used in a started (frozen) assessment cannot be deleted."
        confirmLabel="Delete question"
        onConfirm={async () => {
          await remove.mutateAsync();
        }}
      />
    </div>
  );
}
