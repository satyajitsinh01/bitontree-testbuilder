"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Paginated } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

interface AuditRow {
  id: string;
  actor_type: string;
  actor_id: string | null;
  action: string;
  entity_type: string;
  entity_id: string;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  created_at: string;
}

export default function AuditPage() {
  const [actionFilter, setActionFilter] = useState("");
  const { data } = useQuery({
    queryKey: ["audit", actionFilter],
    queryFn: () =>
      api<Paginated<AuditRow>>(
        `/admin/audit-logs?size=100${actionFilter ? `&action=${actionFilter}` : ""}`,
        { token: "admin" }
      ),
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Audit Log</h1>
        <p className="text-sm text-muted-foreground">
          Immutable record of sensitive actions: edits, timing changes, invitations,
          score overrides, session resets.
        </p>
      </div>
      <Input
        placeholder="Filter by exact action, e.g. score.overridden"
        value={actionFilter}
        onChange={(e) => setActionFilter(e.target.value)}
        className="max-w-sm"
      />
      <div className="rounded-lg border bg-background">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>When</TableHead>
              <TableHead>Action</TableHead>
              <TableHead>Entity</TableHead>
              <TableHead>Change</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data?.items.map((row) => (
              <TableRow key={row.id}>
                <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                  {new Date(row.created_at + "Z").toLocaleString()}
                </TableCell>
                <TableCell>
                  <Badge variant="outline">{row.action}</Badge>
                </TableCell>
                <TableCell className="text-xs">
                  {row.entity_type}
                  <span className="text-muted-foreground"> {row.entity_id.slice(0, 8)}…</span>
                </TableCell>
                <TableCell className="max-w-md">
                  <pre className="text-xs text-muted-foreground truncate">
                    {row.after ? JSON.stringify(row.after) : "—"}
                  </pre>
                </TableCell>
              </TableRow>
            ))}
            {data && data.items.length === 0 && (
              <TableRow>
                <TableCell colSpan={4} className="text-center text-muted-foreground py-8">
                  No audit entries match.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
