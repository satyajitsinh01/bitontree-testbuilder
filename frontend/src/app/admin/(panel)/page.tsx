"use client";

import Link from "next/link";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, errorText } from "@/lib/api";
import type { Paginated } from "@/lib/types";
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
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { Plus } from "lucide-react";

interface AssessmentRow {
  id: string;
  title: string;
  status: string;
  created_at: string;
}

const STATUS_VARIANT: Record<string, "default" | "secondary" | "outline"> = {
  published: "default",
  draft: "secondary",
  archived: "outline",
};

export default function AssessmentsPage() {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [windowStart, setWindowStart] = useState("");
  const [windowEnd, setWindowEnd] = useState("");
  const windowValid =
    Boolean(windowStart && windowEnd) &&
    new Date(windowEnd).getTime() > new Date(windowStart).getTime() &&
    new Date(windowEnd).getTime() > Date.now() &&
    (new Date(windowEnd).getTime() - new Date(windowStart).getTime()) % 60000 === 0;

  const { data, isLoading } = useQuery({
    queryKey: ["assessments"],
    queryFn: () =>
      api<Paginated<AssessmentRow>>("/assessments?size=100", { token: "admin" }),
  });

  const create = useMutation({
    mutationFn: () =>
      api<{ id: string }>("/assessments", {
        token: "admin",
        body: {
          title,
          description,
          window_start_at: new Date(windowStart).toISOString(),
          window_end_at: new Date(windowEnd).toISOString(),
        },
      }),
    onSuccess: () => {
      toast.success("Assessment created");
      setOpen(false);
      setTitle("");
      setDescription("");
      setWindowStart("");
      setWindowEnd("");
      queryClient.invalidateQueries({ queryKey: ["assessments"] });
    },
    onError: (error) => toast.error(errorText(error)),
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Assessments</h1>
          <p className="text-sm text-muted-foreground">
            Create tests, build sections, and manage candidates.
          </p>
        </div>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger render={<Button className="gap-2" />}>
            <Plus className="h-4 w-4" /> New assessment
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>New assessment</DialogTitle>
            </DialogHeader>
            <div className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="title">Title</Label>
                <Input id="title" value={title} onChange={(e) => setTitle(e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="description">Description</Label>
                <Textarea
                  id="description"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="window-start">Start time</Label>
                  <Input
                    id="window-start"
                    type="datetime-local"
                    value={windowStart}
                    onChange={(event) => setWindowStart(event.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="window-end">End time</Label>
                  <Input
                    id="window-end"
                    type="datetime-local"
                    value={windowEnd}
                    onChange={(event) => setWindowEnd(event.target.value)}
                  />
                </div>
              </div>
              <p className="text-xs text-muted-foreground">
                Section durations must add up to this complete assessment window.
              </p>
              <Button
                onClick={() => create.mutate()}
                disabled={title.trim().length < 3 || !windowValid || create.isPending}
                className="w-full"
              >
                Create
              </Button>
            </div>
          </DialogContent>
        </Dialog>
      </div>

      <div className="rounded-lg border bg-background">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Title</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Created</TableHead>
              <TableHead className="w-24" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && (
              <TableRow>
                <TableCell colSpan={4} className="text-center text-muted-foreground py-8">
                  Loading…
                </TableCell>
              </TableRow>
            )}
            {data?.items.map((row) => (
              <TableRow key={row.id}>
                <TableCell className="font-medium">{row.title}</TableCell>
                <TableCell>
                  <Badge variant={STATUS_VARIANT[row.status] ?? "secondary"}>
                    {row.status}
                  </Badge>
                </TableCell>
                <TableCell className="text-muted-foreground">
                  {new Date(row.created_at).toLocaleString()}
                </TableCell>
                <TableCell>
                  <Button
                    render={<Link href={`/admin/assessments/${row.id}`} />}
                    variant="outline"
                    size="sm"
                  >
                    Open
                  </Button>
                </TableCell>
              </TableRow>
            ))}
            {data && data.items.length === 0 && (
              <TableRow>
                <TableCell colSpan={4} className="text-center text-muted-foreground py-8">
                  No assessments yet — create your first one.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
