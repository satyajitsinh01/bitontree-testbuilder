"use client";

import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, errorText, getToken } from "@/lib/api";
import type { AssignmentOut, Paginated } from "@/lib/types";
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
import { Mail, Plus, RotateCcw, Trash2, Upload } from "lucide-react";

function toLocalInputValue(offsetMinutes: number): string {
  const date = new Date(Date.now() + offsetMinutes * 60000);
  date.setSeconds(0, 0);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function AddCandidateDialog({
  assessmentId,
  onDone,
}: {
  assessmentId: string;
  onDone: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [startAt, setStartAt] = useState(toLocalInputValue(0));
  const [endAt, setEndAt] = useState(toLocalInputValue(240));
  const [sendEmail, setSendEmail] = useState(true);
  const [credentials, setCredentials] = useState<AssignmentOut | null>(null);

  const add = useMutation({
    mutationFn: () =>
      api<AssignmentOut>(`/assessments/${assessmentId}/assignments`, {
        token: "admin",
        body: {
          full_name: fullName,
          email,
          phone,
          window_start_at: new Date(startAt).toISOString(),
          window_end_at: new Date(endAt).toISOString(),
          send_email: sendEmail,
        },
      }),
    onSuccess: (data) => {
      toast.success("Candidate added");
      setCredentials(data);
      onDone();
    },
    onError: (error) => toast.error(errorText(error)),
  });

  function reset() {
    setCredentials(null);
    setFullName("");
    setEmail("");
    setPhone("");
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) reset();
      }}
    >
      <DialogTrigger render={<Button className="gap-2" />}>
        <Plus className="h-4 w-4" /> Add candidate
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add candidate</DialogTitle>
        </DialogHeader>
        {credentials ? (
          <div className="space-y-3">
            <p className="text-sm">
              Credentials generated — shown once. The invitation email
              {credentials.send_email ? " was sent." : " was NOT sent (toggle off)."}
            </p>
            <div className="rounded-md bg-muted p-4 font-mono text-sm space-y-1">
              <p>Username: {credentials.username}</p>
              <p>Password: {credentials.initial_password}</p>
            </div>
            <Button className="w-full" onClick={() => setOpen(false)}>
              Done
            </Button>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Full name</Label>
                <Input value={fullName} onChange={(e) => setFullName(e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label>Email</Label>
                <Input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label>Phone</Label>
              <Input value={phone} onChange={(e) => setPhone(e.target.value)} />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Window start</Label>
                <Input
                  type="datetime-local"
                  value={startAt}
                  onChange={(e) => setStartAt(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label>Window end</Label>
                <Input
                  type="datetime-local"
                  value={endAt}
                  onChange={(e) => setEndAt(e.target.value)}
                />
              </div>
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={sendEmail}
                onChange={(e) => setSendEmail(e.target.checked)}
              />
              Send invitation email
            </label>
            <Button
              className="w-full"
              onClick={() => add.mutate()}
              disabled={!fullName.trim() || !email.trim() || add.isPending}
            >
              Add candidate
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

function ImportButton({
  assessmentId,
  onDone,
}: {
  assessmentId: string;
  onDone: () => void;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);

  async function upload(file: File) {
    setBusy(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
      const response = await fetch(
        `${base}/api/v1/assessments/${assessmentId}/assignments/import`,
        {
          method: "POST",
          headers: { Authorization: `Bearer ${getToken("admin")}` },
          body: form,
        }
      );
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error?.code ?? "import failed");
      const data = payload.data;
      toast.success(
        `Imported ${data.imported_rows}/${data.total_rows} rows` +
          (data.failed_rows ? ` — ${data.failed_rows} failed (see batch report)` : "")
      );
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
        accept=".csv,.xlsx"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) upload(file);
        }}
      />
      <Button
        variant="outline"
        className="gap-2"
        disabled={busy}
        onClick={() => fileRef.current?.click()}
      >
        <Upload className="h-4 w-4" /> {busy ? "Importing…" : "Import CSV/Excel"}
      </Button>
    </>
  );
}

const STATUS_COLORS: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
  completed: "default",
  in_progress: "secondary",
  invited: "outline",
  not_started: "outline",
  expired: "destructive",
};

export function CandidatesTab({
  assessmentId,
  published,
}: {
  assessmentId: string;
  published: boolean;
}) {
  const queryClient = useQueryClient();
  const { data } = useQuery({
    queryKey: ["assignments", assessmentId],
    queryFn: () =>
      api<Paginated<AssignmentOut>>(`/assessments/${assessmentId}/assignments?size=100`, {
        token: "admin",
      }),
  });

  const refresh = () =>
    queryClient.invalidateQueries({ queryKey: ["assignments", assessmentId] });

  const resend = useMutation({
    mutationFn: (id: string) =>
      api(`/assignments/${id}/resend-invitation`, {
        token: "admin",
        method: "POST",
        body: {},
      }),
    onSuccess: () => toast.success("Invitation resent with fresh credentials"),
    onError: (error) => toast.error(errorText(error)),
  });

  const remove = useMutation({
    mutationFn: (id: string) =>
      api(`/assignments/${id}?confirm=true`, { token: "admin", method: "DELETE" }),
    onSuccess: () => {
      toast.success("Candidate removed");
      refresh();
    },
    onError: (error) => toast.error(errorText(error)),
  });

  const recover = useMutation({
    mutationFn: (id: string) =>
      api(`/assignments/${id}/sessions`, { token: "admin", method: "POST", body: {} }),
    onSuccess: () => {
      toast.success("Session reset — candidate can log in again");
      refresh();
    },
    onError: (error) => toast.error(errorText(error)),
  });

  return (
    <div className="space-y-4">
      {!published && (
        <p className="rounded-md border border-amber-300 bg-amber-50 px-4 py-2 text-sm text-amber-900">
          Publish the assessment before candidates can start their exam.
        </p>
      )}
      <div className="flex justify-end gap-2">
        <ImportButton assessmentId={assessmentId} onDone={refresh} />
        <AddCandidateDialog assessmentId={assessmentId} onDone={refresh} />
      </div>
      <div className="rounded-lg border bg-background">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Candidate</TableHead>
              <TableHead>Username</TableHead>
              <TableHead>Window</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="w-40" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {data?.items.map((row) => (
              <TableRow key={row.id}>
                <TableCell>
                  <p className="font-medium">{row.candidate.full_name}</p>
                  <p className="text-xs text-muted-foreground">{row.candidate.email}</p>
                </TableCell>
                <TableCell className="font-mono text-xs">{row.username}</TableCell>
                <TableCell className="text-xs text-muted-foreground">
                  {new Date(row.window_start_at + "Z").toLocaleString()} →{" "}
                  {new Date(row.window_end_at + "Z").toLocaleString()}
                </TableCell>
                <TableCell>
                  <Badge variant={STATUS_COLORS[row.status] ?? "outline"}>
                    {row.status}
                  </Badge>
                </TableCell>
                <TableCell>
                  <div className="flex gap-1">
                    <Button
                      size="icon"
                      variant="ghost"
                      title="Resend invitation"
                      onClick={() => resend.mutate(row.id)}
                    >
                      <Mail className="h-4 w-4" />
                    </Button>
                    <Button
                      size="icon"
                      variant="ghost"
                      title="Reset session"
                      onClick={() => recover.mutate(row.id)}
                    >
                      <RotateCcw className="h-4 w-4" />
                    </Button>
                    <Button
                      size="icon"
                      variant="ghost"
                      title="Remove candidate"
                      onClick={() => remove.mutate(row.id)}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
            {data && data.items.length === 0 && (
              <TableRow>
                <TableCell colSpan={5} className="text-center text-muted-foreground py-8">
                  No candidates yet — add one or import a CSV.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
