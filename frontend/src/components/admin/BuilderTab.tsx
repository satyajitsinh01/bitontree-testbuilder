"use client";

import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, errorText } from "@/lib/api";
import type { AssessmentOut, Paginated, QuestionOut, SectionOut } from "@/lib/types";
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
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Pencil, Rocket, Trash2 } from "lucide-react";

function AddSectionDialog({
  assessmentId,
  allocatedWeight,
  allocatedDuration,
  availableDuration,
  onChanged,
}: {
  assessmentId: string;
  allocatedWeight: number;
  allocatedDuration: number;
  availableDuration: number;
  onChanged: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [duration, setDuration] = useState(15);
  const [weightage, setWeightage] = useState(50);
  const [isFinal, setIsFinal] = useState(false);
  const remainingWeight = Math.max(0, 100 - allocatedWeight);
  const remainingDuration = Math.max(0, availableDuration - allocatedDuration);

  const add = useMutation({
    mutationFn: () =>
      api(`/assessments/${assessmentId}/sections`, {
        token: "admin",
        body: {
          name,
          duration_min: duration,
          weightage_pct: weightage,
          question_count: 0,
          is_final: isFinal,
        },
      }),
    onSuccess: () => {
      toast.success("Section added");
      setOpen(false);
      setName("");
      onChanged();
    },
    onError: (error) => toast.error(errorText(error)),
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button variant="outline" />}>Add section</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add section</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label>Name</Label>
            <Input
              value={name}
              placeholder="e.g. Aptitude, DSA, English"
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label>Duration (minutes)</Label>
              <Input
                type="number"
                min={1}
                max={remainingDuration}
                value={duration}
                onChange={(e) => setDuration(Number(e.target.value))}
              />
            </div>
            <div className="space-y-2">
              <Label>Weightage (%)</Label>
              <Input
                type="number"
                min={0}
                max={remainingWeight}
                step={0.01}
                value={weightage}
                onChange={(e) => setWeightage(Number(e.target.value))}
              />
              <p className="text-xs text-muted-foreground">
                {allocatedDuration} min allocated · {remainingDuration} min remaining
              </p>
              <p className="text-xs text-muted-foreground">
                {allocatedWeight}% allocated · {remainingWeight}% remaining
              </p>
            </div>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={isFinal}
              onChange={(e) => setIsFinal(e.target.checked)}
            />
            Final section (ends with “Submit and End Test”)
          </label>
          <Button
            className="w-full"
            onClick={() => add.mutate()}
            disabled={
              !name.trim() ||
              weightage < 0 ||
              weightage > remainingWeight ||
              duration < 1 ||
              duration > remainingDuration ||
              add.isPending
            }
          >
            Add section
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function EditSectionDialog({
  section,
  allocatedWeight,
  allocatedDuration,
  availableDuration,
  frozen,
  onChanged,
}: {
  section: SectionOut;
  allocatedWeight: number;
  allocatedDuration: number;
  availableDuration: number;
  frozen: boolean;
  onChanged: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState(section.name);
  const [duration, setDuration] = useState(section.duration_min);
  const [weightage, setWeightage] = useState(section.weightage_pct);
  const [isFinal, setIsFinal] = useState(section.is_final);
  // remaining budget excludes this section's own current allocation
  const remainingWeight = Math.max(0, 100 - (allocatedWeight - section.weightage_pct));
  const remainingDuration = Math.max(
    0,
    availableDuration - (allocatedDuration - section.duration_min)
  );

  const save = useMutation({
    mutationFn: () =>
      api(`/sections/${section.id}`, {
        token: "admin",
        method: "PATCH",
        body: {
          name,
          duration_min: duration,
          weightage_pct: weightage,
          question_count: section.question_count,
          is_final: isFinal,
        },
      }),
    onSuccess: () => {
      toast.success("Section updated");
      setOpen(false);
      onChanged();
    },
    onError: (error) => toast.error(errorText(error)),
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger
        render={<Button size="icon" variant="ghost" title="Edit section" />}
      >
        <Pencil className="h-4 w-4" />
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Edit section</DialogTitle>
        </DialogHeader>
        {frozen ? (
          <p className="rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
            This version is frozen because candidates have started. Edit the assessment
            details first to fork a new draft version, then edit its sections.
          </p>
        ) : (
          <div className="space-y-4">
            <div className="space-y-2">
              <Label>Name</Label>
              <Input value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Duration (minutes)</Label>
                <Input
                  type="number"
                  min={1}
                  max={remainingDuration}
                  value={duration}
                  onChange={(e) => setDuration(Number(e.target.value))}
                />
                <p className="text-xs text-muted-foreground">
                  {remainingDuration} min available for this section
                </p>
              </div>
              <div className="space-y-2">
                <Label>Weightage (%)</Label>
                <Input
                  type="number"
                  min={0}
                  max={remainingWeight}
                  step={0.01}
                  value={weightage}
                  onChange={(e) => setWeightage(Number(e.target.value))}
                />
                <p className="text-xs text-muted-foreground">
                  {remainingWeight}% available for this section
                </p>
              </div>
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={isFinal}
                onChange={(e) => setIsFinal(e.target.checked)}
              />
              Final section (ends with “Submit and End Test”)
            </label>
            <Button
              className="w-full"
              onClick={() => save.mutate()}
              disabled={
                !name.trim() ||
                weightage < 0 ||
                weightage > remainingWeight ||
                duration < 1 ||
                duration > remainingDuration ||
                save.isPending
              }
            >
              {save.isPending ? "Saving…" : "Save changes"}
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

function SectionQuestionsDialog({
  section,
  onChanged,
}: {
  section: SectionOut;
  onChanged: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [poolCount, setPoolCount] = useState(0);

  const { data: bank } = useQuery({
    queryKey: ["questions", "active-picker"],
    queryFn: () =>
      api<Paginated<QuestionOut>>("/questions?size=100&status=active", { token: "admin" }),
    enabled: open,
  });

  const save = useMutation({
    mutationFn: async () => {
      const ids = Array.from(selected);
      const usePool = poolCount > 0 && poolCount < ids.length;
      await api(`/sections/${section.id}/questions`, {
        token: "admin",
        method: "PUT",
        body: {
          items: ids.map((id) => ({
            question_id: id,
            pool_group: usePool ? "pool" : null,
            points: 1,
          })),
        },
      });
      await api(`/sections/${section.id}/pool-rules`, {
        token: "admin",
        method: "PUT",
        body: { items: usePool ? [{ pool_group: "pool", select_count: poolCount }] : [] },
      });
    },
    onSuccess: () => {
      toast.success("Section questions saved");
      setOpen(false);
      onChanged();
    },
    onError: (error) => toast.error(errorText(error)),
  });

  function toggle(id: string) {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelected(next);
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button size="sm" variant="outline" />}>
        Pick questions ({section.questions.length})
      </DialogTrigger>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Questions for “{section.name}”</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-1 max-h-80 overflow-y-auto rounded border p-2">
            {bank?.items.map((q) => (
              <label
                key={q.id}
                className="flex items-center gap-2 rounded p-2 text-sm hover:bg-muted cursor-pointer"
              >
                <input
                  type="checkbox"
                  checked={selected.has(q.id)}
                  onChange={() => toggle(q.id)}
                />
                <Badge variant="outline">{q.current_version?.qtype}</Badge>
                <span className="truncate">{q.current_version?.title}</span>
              </label>
            ))}
            {bank && bank.items.length === 0 && (
              <p className="p-4 text-sm text-muted-foreground">
                No active questions — create or approve some in the Question Bank first.
              </p>
            )}
          </div>
          <div className="flex items-end gap-3">
            <div className="space-y-2">
              <Label>Random pool: deliver N of {selected.size} selected (0 = all)</Label>
              <Input
                type="number"
                min={0}
                max={selected.size}
                value={poolCount}
                onChange={(e) => setPoolCount(Number(e.target.value))}
                className="w-40"
              />
            </div>
            <Button
              onClick={() => save.mutate()}
              disabled={selected.size === 0 || save.isPending}
            >
              Save
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export function BuilderTab({
  assessment,
  onChanged,
}: {
  assessment: AssessmentOut;
  onChanged: () => void;
}) {
  const publish = useMutation({
    mutationFn: () =>
      api(`/assessments/${assessment.id}/publish`, {
        token: "admin",
        method: "POST",
        body: {},
      }),
    onSuccess: () => {
      toast.success("Assessment published");
      onChanged();
    },
    onError: (error) => toast.error(errorText(error)),
  });

  const deleteSection = useMutation({
    mutationFn: (sectionId: string) =>
      api(`/sections/${sectionId}`, { token: "admin", method: "DELETE" }),
    onSuccess: () => {
      toast.success("Section deleted");
      onChanged();
    },
    onError: (error) => toast.error(errorText(error)),
  });

  const sections = assessment.version?.sections ?? [];
  const totalWeight = sections.reduce((sum, s) => sum + s.weightage_pct, 0);
  const totalDuration = sections.reduce((sum, s) => sum + s.duration_min, 0);
  const availableDuration =
    assessment.window_start_at && assessment.window_end_at
      ? Math.round(
          (new Date(`${assessment.window_end_at}Z`).getTime() -
            new Date(`${assessment.window_start_at}Z`).getTime()) /
            60000
        )
      : 0;
  const weightageComplete = Math.round(totalWeight * 100) / 100 === 100;
  const durationComplete = totalDuration === availableDuration;
  const frozen = assessment.version?.frozen ?? false;

  return (
    <div className="space-y-4">
      {frozen && (
        <p className="rounded-lg border bg-muted/60 px-4 py-2.5 text-sm text-muted-foreground">
          This version is frozen because candidates have started it. Editing the
          assessment details creates a new version automatically; section edits require
          that fork first.
        </p>
      )}
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          {sections.length} sections · total weightage {totalWeight}% · total{" "}
          {sections.reduce((sum, s) => sum + s.duration_min, 0)} min
        </p>
        <div className="flex gap-2">
          <AddSectionDialog
            assessmentId={assessment.id}
            allocatedWeight={totalWeight}
            allocatedDuration={totalDuration}
            availableDuration={availableDuration}
            onChanged={onChanged}
          />
          <Button
            onClick={() => publish.mutate()}
            disabled={publish.isPending || !weightageComplete || !durationComplete}
            className="gap-2"
            title={weightageComplete ? undefined : "Section weightages must total exactly 100%"}
          >
            <Rocket className="h-4 w-4" />
            {assessment.status === "published" ? "Republish" : "Publish"}
          </Button>
        </div>
      </div>
      {!weightageComplete && (
        <p className="text-sm text-destructive">
          Publishing is available only when section weightages total exactly 100%
          (currently {totalWeight}%).
        </p>
      )}
      {!durationComplete && (
        <p className="text-sm text-destructive">
          Section durations must total exactly {availableDuration} minutes for the fixed
          assessment window (currently {totalDuration} minutes).
        </p>
      )}
      <div className="grid gap-4">
        {sections.map((section) => (
          <Card key={section.id}>
            <CardHeader className="flex flex-row items-center justify-between space-y-0">
              <CardTitle className="text-base flex items-center gap-2">
                {section.order_index + 1}. {section.name}
                {section.is_final && <Badge variant="secondary">final</Badge>}
              </CardTitle>
              <div className="flex items-center gap-1">
                <SectionQuestionsDialog section={section} onChanged={onChanged} />
                <EditSectionDialog
                  section={section}
                  allocatedWeight={totalWeight}
                  allocatedDuration={totalDuration}
                  availableDuration={availableDuration}
                  frozen={frozen}
                  onChanged={onChanged}
                />
                <ConfirmDialog
                  trigger={
                    <Button size="icon" variant="ghost" title="Delete section">
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  }
                  title="Delete this section?"
                  description={
                    <>
                      Section <strong>{section.name}</strong> and its attached questions
                      and pool rules will be removed from the assessment.
                    </>
                  }
                  warning={
                    frozen
                      ? "This version is frozen. Edit the assessment details first to fork a new draft version."
                      : "This cannot be undone. Remaining section weightages must still total 100% before you can publish."
                  }
                  confirmLabel="Delete section"
                  onConfirm={async () => {
                    await deleteSection.mutateAsync(section.id);
                  }}
                />
              </div>
            </CardHeader>
            <CardContent className="text-sm text-muted-foreground flex gap-6">
              <span>{section.duration_min} min</span>
              <span>{section.weightage_pct}% weight</span>
              <span>{section.questions.length} questions attached</span>
              {section.pool_rules.map((rule) => (
                <span key={rule.pool_group}>
                  pool: pick {rule.select_count} of{" "}
                  {section.questions.filter((q) => q.pool_group === rule.pool_group).length}
                </span>
              ))}
            </CardContent>
          </Card>
        ))}
        {sections.length === 0 && (
          <p className="text-sm text-muted-foreground py-8 text-center border rounded-lg">
            No sections yet. Add your first section (e.g. Aptitude, Coding).
          </p>
        )}
      </div>
    </div>
  );
}
