"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, errorText } from "@/lib/api";
import type { Paginated, QuestionOut } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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
import {
  AiGenerateDialog,
  ImportQuestionsDialog,
  NewQuestionDialog,
} from "@/components/admin/QuestionDialogs";
import { FileJson, Sparkles } from "lucide-react";

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
            MCQ, written, and coding questions. AI-generated and imported questions
            land as drafts and require approval.
          </p>
        </div>
        <div className="flex gap-2">
          <NewQuestionDialog onDone={refresh} />
          <ImportQuestionsDialog onDone={refresh} />
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
            <SelectItem value="draft">Drafts</SelectItem>
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
                  ) : q.source === "import" ? (
                    <Badge variant="secondary" className="gap-1">
                      <FileJson className="h-3 w-3" /> import
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
