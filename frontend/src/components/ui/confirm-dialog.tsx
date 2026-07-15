"use client";

import { useState } from "react";
import { AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";

/**
 * Reusable confirmation modal. Wrap a trigger element; the modal shows a title,
 * a warning body, and Cancel / Confirm actions. `onConfirm` may be async — the
 * confirm button shows a pending state and the modal closes on success.
 */
export function ConfirmDialog({
  trigger,
  title,
  description,
  warning,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  destructive = true,
  onConfirm,
}: {
  trigger: React.ReactElement;
  title: string;
  description?: React.ReactNode;
  warning?: React.ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  destructive?: boolean;
  onConfirm: () => void | Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  async function confirm() {
    setBusy(true);
    try {
      await onConfirm();
      setOpen(false);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !busy && setOpen(next)}>
      <DialogTrigger render={trigger} />
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {destructive && <AlertTriangle className="h-5 w-5 text-destructive" />}
            {title}
          </DialogTitle>
        </DialogHeader>
        {description && <p className="text-sm text-muted-foreground">{description}</p>}
        {warning && (
          <p className="rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
            {warning}
          </p>
        )}
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="outline" onClick={() => setOpen(false)} disabled={busy}>
            {cancelLabel}
          </Button>
          <Button
            variant={destructive ? "destructive" : "default"}
            onClick={confirm}
            disabled={busy}
          >
            {busy ? "Working…" : confirmLabel}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
