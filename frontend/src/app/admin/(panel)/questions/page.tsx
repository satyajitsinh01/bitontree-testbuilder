"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, errorText } from "@/lib/api";
import type { Paginated, QuestionOut } from "@/lib/types";
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { Plus, Sparkles } from "lucide-react";

function NewQuestionDialog({ onDone }: { onDone: () => void }) {
  const [open, setOpen] = useState(false);
  const [qtype, setQtype] = useState<"mcq" | "text" | "coding">("mcq");
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [difficulty, setDifficulty] = useState("medium");
  const [options, setOptions] = useState(["", "", "", ""]);
  const [correctIndex, setCorrectIndex] = useState(0);
  const [rubric, setRubric] = useState("");

  const create = useMutation({
    mutationFn: () => {
      let config: Record<string, unknown> = {};
      let answerType = "single_choice";
      if (qtype === "mcq") {
        const opts = options
          .map((text, i) => ({ id: `o${i}`, text: text.trim() }))
          .filter((o) => o.text);
        config = { options: opts, correct_option_ids: [`o${correctIndex}`] };
      } else if (qtype === "text") {
        config = { rubric };
        answerType = "long_text";
      } else {
        config = {
          allowed_languages: ["python", "javascript", "java", "cpp"],
          starter_code: { python: "def solve():\n    pass\n" },
          test_cases: [
            { id: "t1", input: "", expected_output: "", is_hidden: false, weight: 1 },
          ],
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
      onDone();
    },
    onError: (error) => toast.error(errorText(error)),
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button variant="outline" className="gap-2" />}>
        <Plus className="h-4 w-4" /> New question
      </DialogTrigger>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>New question</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label>Type</Label>
              <Select
                value={qtype}
                onValueChange={(v) => v && setQtype(v as typeof qtype)}
              >
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
              <Select value={difficulty} onValueChange={(v) => v && setDifficulty(v)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="easy">Easy</SelectItem>
                  <SelectItem value="medium">Medium</SelectItem>
                  <SelectItem value="hard">Hard</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="space-y-2">
            <Label>Title</Label>
            <Input value={title} onChange={(e) => setTitle(e.target.value)} />
          </div>
          <div className="space-y-2">
            <Label>Question body</Label>
            <Textarea value={body} onChange={(e) => setBody(e.target.value)} />
          </div>
          {qtype === "mcq" && (
            <div className="space-y-2">
              <Label>Options (select the correct one)</Label>
              {options.map((opt, i) => (
                <div key={i} className="flex items-center gap-2">
                  <input
                    type="radio"
                    name="correct"
                    checked={correctIndex === i}
                    onChange={() => setCorrectIndex(i)}
                  />
                  <Input
                    value={opt}
                    placeholder={`Option ${i + 1}`}
                    onChange={(e) =>
                      setOptions(options.map((o, j) => (j === i ? e.target.value : o)))
                    }
                  />
                </div>
              ))}
            </div>
          )}
          {qtype === "text" && (
            <div className="space-y-2">
              <Label>Evaluation rubric</Label>
              <Textarea value={rubric} onChange={(e) => setRubric(e.target.value)} />
            </div>
          )}
          {qtype === "coding" && (
            <p className="text-sm text-muted-foreground">
              A starter coding question is created with one visible test case — edit
              test cases afterwards via the API or a follow-up edit.
            </p>
          )}
          <Button
            className="w-full"
            onClick={() => create.mutate()}
            disabled={title.trim().length < 3 || create.isPending}
          >
            Create question
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function AiGenerateDialog({ onDone }: { onDone: () => void }) {
  const [open, setOpen] = useState(false);
  const [prompt, setPrompt] = useState("");
  const [topic, setTopic] = useState("");
  const [qtype, setQtype] = useState("mcq");
  const [count, setCount] = useState(5);

  const generate = useMutation({
    mutationFn: () =>
      api<{ status: string; question_ids: string[] }>("/questions/ai-generate", {
        token: "admin",
        body: { prompt, qtype, count, topic: topic || "general", difficulty: "medium" },
      }),
    onSuccess: (data) => {
      if (data.status === "completed") {
        toast.success(`${data.question_ids.length} draft questions generated — review and approve them.`);
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
          <div className="grid grid-cols-3 gap-3">
            <div className="space-y-2">
              <Label>Topic</Label>
              <Input value={topic} onChange={(e) => setTopic(e.target.value)} />
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
            AI questions are created as drafts and must be approved before they can be
            used in an assessment.
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

export default function QuestionBankPage() {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<string>("all");

  const { data, isLoading } = useQuery({
    queryKey: ["questions", statusFilter],
    queryFn: () =>
      api<Paginated<QuestionOut>>(
        `/questions?size=100${statusFilter !== "all" ? `&status=${statusFilter}` : ""}`,
        { token: "admin" }
      ),
  });

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["questions"] });

  const approve = useMutation({
    mutationFn: (id: string) =>
      api(`/questions/${id}/approve`, { token: "admin", method: "POST", body: {} }),
    onSuccess: () => {
      toast.success("Question approved and activated");
      refresh();
    },
    onError: (error) => toast.error(errorText(error)),
  });

  const setStatus = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      api(`/questions/${id}/status`, { token: "admin", body: { status } }),
    onSuccess: refresh,
    onError: (error) => toast.error(errorText(error)),
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Question Bank</h1>
          <p className="text-sm text-muted-foreground">
            Central bank of MCQ, written, and coding questions. AI drafts require approval.
          </p>
        </div>
        <div className="flex gap-2">
          <NewQuestionDialog onDone={refresh} />
          <AiGenerateDialog onDone={refresh} />
        </div>
      </div>

      <div className="flex items-center gap-2">
        <Label className="text-sm">Status</Label>
        <Select value={statusFilter} onValueChange={(v) => v && setStatusFilter(v)}>
          <SelectTrigger className="w-40">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All</SelectItem>
            <SelectItem value="active">Active</SelectItem>
            <SelectItem value="draft">Drafts (AI)</SelectItem>
            <SelectItem value="inactive">Inactive</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="rounded-lg border bg-background">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Title</TableHead>
              <TableHead>Type</TableHead>
              <TableHead>Difficulty</TableHead>
              <TableHead>Source</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="w-44" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && (
              <TableRow>
                <TableCell colSpan={6} className="text-center text-muted-foreground py-8">
                  Loading…
                </TableCell>
              </TableRow>
            )}
            {data?.items.map((q) => (
              <TableRow key={q.id}>
                <TableCell className="font-medium max-w-md truncate">
                  {q.current_version?.title}
                </TableCell>
                <TableCell>
                  <Badge variant="outline">{q.current_version?.qtype}</Badge>
                </TableCell>
                <TableCell>{q.current_version?.difficulty}</TableCell>
                <TableCell>
                  {q.source === "ai" ? (
                    <Badge variant="secondary" className="gap-1">
                      <Sparkles className="h-3 w-3" /> AI
                    </Badge>
                  ) : (
                    "manual"
                  )}
                </TableCell>
                <TableCell>
                  <Badge variant={q.status === "active" ? "default" : "secondary"}>
                    {q.status}
                  </Badge>
                </TableCell>
                <TableCell className="space-x-2">
                  {q.status === "draft" && (
                    <Button size="sm" onClick={() => approve.mutate(q.id)}>
                      Approve
                    </Button>
                  )}
                  {q.status === "active" && (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => setStatus.mutate({ id: q.id, status: "inactive" })}
                    >
                      Deactivate
                    </Button>
                  )}
                  {q.status === "inactive" && (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => setStatus.mutate({ id: q.id, status: "active" })}
                    >
                      Activate
                    </Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
            {data && data.items.length === 0 && (
              <TableRow>
                <TableCell colSpan={6} className="text-center text-muted-foreground py-8">
                  No questions match this filter.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
