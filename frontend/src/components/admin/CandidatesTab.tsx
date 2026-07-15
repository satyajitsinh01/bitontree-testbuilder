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
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Mail, Pencil, Plus, RotateCcw, Trash2, Upload } from "lucide-react";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
// Indian mobile: exactly 10 digits starting 6-9, optional +91 prefix
const INDIAN_MOBILE_RE = /^(?:\+91)?[6-9]\d{9}$/;

function normalizePhone(raw: string): string {
  return raw.replace(/[\s()-]/g, "");
}

type CandidateForm = {
  fullName: string;
  email: string;
  phone: string;
};

function validateCandidate(form: CandidateForm): Partial<Record<keyof CandidateForm, string>> {
  const errors: Partial<Record<keyof CandidateForm, string>> = {};
  if (form.fullName.trim().length < 2) errors.fullName = "Enter the candidate's full name.";
  if (!form.email.trim()) errors.email = "Email is required.";
  else if (!EMAIL_RE.test(form.email.trim())) errors.email = "Enter a valid email address.";
  if (form.phone.trim() && !INDIAN_MOBILE_RE.test(normalizePhone(form.phone)))
    errors.phone = "Enter a valid 10-digit Indian mobile number (starts with 6-9, +91 optional).";
  return errors;
}

function FieldError({ message }: { message?: string }) {
  if (!message) return null;
  return <p className="text-xs font-medium text-destructive">{message}</p>;
}

function AddCandidateDialog({
  assessmentId,
  onDone,
}: {
  assessmentId: string;
  onDone: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<CandidateForm>({
    fullName: "",
    email: "",
    phone: "",
  });
  const [touched, setTouched] = useState<Partial<Record<keyof CandidateForm, boolean>>>({});
  const [sendEmail, setSendEmail] = useState(true);
  const [credentials, setCredentials] = useState<AssignmentOut | null>(null);

  const errors = validateCandidate(form);
  const isValid = Object.keys(errors).length === 0;

  function field(name: keyof CandidateForm) {
    return {
      value: form[name],
      onChange: (e: React.ChangeEvent<HTMLInputElement>) =>
        setForm((prev) => ({ ...prev, [name]: e.target.value })),
      onBlur: () => setTouched((prev) => ({ ...prev, [name]: true })),
      "aria-invalid": touched[name] && !!errors[name],
    };
  }

  const add = useMutation({
    mutationFn: () =>
      api<AssignmentOut>(`/assessments/${assessmentId}/assignments`, {
        token: "admin",
        body: {
          full_name: form.fullName.trim(),
          email: form.email.trim(),
          phone: normalizePhone(form.phone),
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

  function submit() {
    setTouched({ fullName: true, email: true, phone: true });
    if (isValid) add.mutate();
  }

  function reset() {
    setCredentials(null);
    setTouched({});
    setForm({
      fullName: "",
      email: "",
      phone: "",
    });
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
            <p className="text-sm">Credentials generated — shown once.</p>
            {credentials.email_status === "sent" && (
              <p className="rounded border bg-muted/40 px-3 py-2 text-sm">
                ✓ Invitation email sent to {credentials.candidate.email}.
              </p>
            )}
            {credentials.email_status === "failed" && (
              <p className="rounded border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
                The invitation email could not be sent — check the mail configuration
                (TB_SMTP_* / TB_RESEND_API_KEY). Use the credentials below or resend
                later.
              </p>
            )}
            {credentials.email_status === "not_sent" && (
              <p className="rounded border bg-muted/40 px-3 py-2 text-sm">
                Email sending was turned off. Share the credentials below directly.
              </p>
            )}
            <div className="rounded-md bg-muted p-4 font-mono text-sm space-y-1">
              <p>Sign-in email: {credentials.candidate.email}</p>
              <p>Password: {credentials.initial_password}</p>
            </div>
            <p className="text-xs text-muted-foreground">
              The candidate signs in on the same login page as admins, using their
              email and this password.
            </p>
            <Button className="w-full" onClick={() => setOpen(false)}>
              Done
            </Button>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label htmlFor="cand-name">Full name</Label>
                <Input id="cand-name" placeholder="Jane Doe" {...field("fullName")} />
                {touched.fullName && <FieldError message={errors.fullName} />}
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="cand-email">Email</Label>
                <Input
                  id="cand-email"
                  type="email"
                  placeholder="jane@example.com"
                  {...field("email")}
                />
                {touched.email && <FieldError message={errors.email} />}
              </div>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="cand-phone">Mobile number (optional)</Label>
              <Input
                id="cand-phone"
                type="tel"
                inputMode="tel"
                maxLength={16}
                placeholder="+91 98765 43210"
                {...field("phone")}
              />
              {touched.phone && <FieldError message={errors.phone} />}
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
              onClick={submit}
              disabled={!isValid || add.isPending}
            >
              {add.isPending ? "Adding…" : "Add candidate"}
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
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [report, setReport] = useState<{
    imported_rows: number;
    total_rows: number;
    failed_rows: number;
    errors: { row: number; error: string }[];
  } | null>(null);

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
      setReport(data);
      onDone();
      if (data.failed_rows) {
        toast.warning(`Imported ${data.imported_rows}/${data.total_rows} rows`);
      } else {
        toast.success(`Imported all ${data.imported_rows} candidates`);
        setOpen(false);
        setFile(null);
      }
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
          const selected = e.target.files?.[0];
          if (selected) {
            setFile(selected);
            setOpen(true);
          }
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
      <Dialog
        open={open}
        onOpenChange={(nextOpen) => {
          setOpen(nextOpen);
          if (!nextOpen && !busy) {
            setFile(null);
            setReport(null);
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Import candidate details</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            CSV columns: studentId, name, email, phone, cgpa
          </p>
          <p className="rounded border bg-muted/40 px-3 py-2 text-sm">{file?.name}</p>
          {report && (
            <div className="space-y-2 rounded-lg border p-3 text-sm">
              <p className="font-medium">
                Imported {report.imported_rows} of {report.total_rows} candidates
              </p>
              {report.errors.length > 0 && (
                <div className="max-h-48 space-y-1 overflow-y-auto text-destructive">
                  {report.errors.map((error) => (
                    <p key={`${error.row}-${error.error}`}>
                      Row {error.row}: {error.error}
                    </p>
                  ))}
                </div>
              )}
            </div>
          )}
          <Button
            onClick={() => file && upload(file)}
            disabled={!file || busy || Boolean(report)}
          >
            {busy ? "Importing…" : "Upload candidates"}
          </Button>
        </DialogContent>
      </Dialog>
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

function EditCandidateDialog({ row, onDone }: { row: AssignmentOut; onDone: () => void }) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState(row.candidate.full_name);
  const [email, setEmail] = useState(row.candidate.email);
  const [phone, setPhone] = useState(row.candidate.phone);
  const [studentId, setStudentId] = useState(row.candidate.student_id ?? "");
  const [cgpa, setCgpa] = useState(row.candidate.cgpa?.toString() ?? "");
  const save = useMutation({
    mutationFn: () =>
      api(`/assignments/${row.id}`, {
        token: "admin",
        method: "PATCH",
        body: {
          full_name: name.trim(),
          email: email.trim(),
          phone: normalizePhone(phone),
          student_id: studentId.trim(),
          cgpa: cgpa === "" ? null : Number(cgpa),
        },
      }),
    onSuccess: () => {
      toast.success("Candidate updated");
      setOpen(false);
      onDone();
    },
    onError: (error) => toast.error(errorText(error)),
  });
  const valid =
    name.trim().length >= 2 &&
    EMAIL_RE.test(email.trim()) &&
    (!phone || INDIAN_MOBILE_RE.test(normalizePhone(phone))) &&
    (cgpa === "" || (Number(cgpa) >= 0 && Number(cgpa) <= 10));

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger
        render={<Button size="icon" variant="ghost" title="Edit candidate" />}
      >
        <Pencil className="h-4 w-4" />
      </DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>Edit candidate</DialogTitle></DialogHeader>
        <div className="grid grid-cols-2 gap-4">
          <Input value={studentId} onChange={(e) => setStudentId(e.target.value)} placeholder="Student ID" />
          <Input type="number" min={0} max={10} step={0.01} value={cgpa} onChange={(e) => setCgpa(e.target.value)} placeholder="CGPA" />
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Name" />
          <Input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Email" />
          <Input className="col-span-2" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="Phone" />
        </div>
        <Button disabled={!valid || save.isPending} onClick={() => save.mutate()}>
          {save.isPending ? "Saving…" : "Save changes"}
        </Button>
      </DialogContent>
    </Dialog>
  );
}

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
    onSuccess: () => toast.success("Invitation email sent with fresh credentials"),
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
        <p className="rounded-lg border bg-muted/60 px-4 py-2.5 text-sm text-muted-foreground">
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
              <TableHead>Student ID</TableHead>
              <TableHead>Candidate</TableHead>
              <TableHead>CGPA</TableHead>
              <TableHead>Username</TableHead>
              <TableHead>Window</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="w-40" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {data?.items.map((row) => (
              <TableRow key={row.id}>
                <TableCell className="font-mono text-xs">
                  {row.candidate.student_id ?? "—"}
                </TableCell>
                <TableCell>
                  <p className="font-medium">{row.candidate.full_name}</p>
                  <p className="text-xs text-muted-foreground">{row.candidate.email}</p>
                </TableCell>
                <TableCell>{row.candidate.cgpa ?? "—"}</TableCell>
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
                    <EditCandidateDialog row={row} onDone={refresh} />
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
                    <ConfirmDialog
                      trigger={
                        <Button size="icon" variant="ghost" title="Remove candidate">
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      }
                      title="Remove this candidate?"
                      description={
                        <>
                          <strong>{row.candidate.full_name}</strong> ({row.candidate.email})
                          will be removed from this assessment and their credentials
                          invalidated.
                        </>
                      }
                      warning="This cannot be undone. Any in-progress exam session for this candidate will be terminated."
                      confirmLabel="Remove candidate"
                      onConfirm={async () => {
                        await remove.mutateAsync(row.id);
                      }}
                    />
                  </div>
                </TableCell>
              </TableRow>
            ))}
            {data && data.items.length === 0 && (
              <TableRow>
                <TableCell colSpan={7} className="text-center text-muted-foreground py-8">
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
