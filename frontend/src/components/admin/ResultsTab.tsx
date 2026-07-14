"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { api, getToken } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Download } from "lucide-react";

interface ResultRow {
  session_id: string;
  candidate: { full_name: string; email: string };
  status: string;
  overall_score: number;
  overall_max: number;
  red_flag_count: number;
  warning_count: number;
  report_status: string;
  rank: number | null;
  percentile: number | null;
}

export function ResultsTab({ assessmentId }: { assessmentId: string }) {
  const { data } = useQuery({
    queryKey: ["results", assessmentId],
    queryFn: () =>
      api<{ items: ResultRow[]; cohort_size: number }>(
        `/assessments/${assessmentId}/results`,
        { token: "admin" }
      ),
    refetchInterval: 15000,
  });

  async function exportCsv() {
    const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    const response = await fetch(
      `${base}/api/v1/assessments/${assessmentId}/results/export`,
      { method: "POST", headers: { Authorization: `Bearer ${getToken("admin")}` } }
    );
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "results.csv";
    link.click();
    URL.revokeObjectURL(url);
  }

  const showRank = data?.items.some((row) => row.rank !== null);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          {data?.cohort_size ?? 0} completed candidates
          {!showRank && data && data.cohort_size > 0 && (
            <> · percentile/rank appear at cohort ≥ 20</>
          )}
        </p>
        <Button variant="outline" className="gap-2" onClick={exportCsv}>
          <Download className="h-4 w-4" /> Export CSV
        </Button>
      </div>
      <div className="rounded-lg border bg-background">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Candidate</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Score</TableHead>
              {showRank && <TableHead>Rank</TableHead>}
              {showRank && <TableHead>Percentile</TableHead>}
              <TableHead>Flags</TableHead>
              <TableHead>Report</TableHead>
              <TableHead className="w-24" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {data?.items.map((row) => (
              <TableRow key={row.session_id}>
                <TableCell>
                  <p className="font-medium">{row.candidate.full_name}</p>
                  <p className="text-xs text-muted-foreground">{row.candidate.email}</p>
                </TableCell>
                <TableCell>
                  <Badge variant="outline">{row.status}</Badge>
                </TableCell>
                <TableCell className="font-medium">
                  {row.overall_score} / {row.overall_max}
                </TableCell>
                {showRank && <TableCell>{row.rank ?? "—"}</TableCell>}
                {showRank && <TableCell>{row.percentile ?? "—"}</TableCell>}
                <TableCell>
                  {row.red_flag_count > 0 && (
                    <Badge variant="destructive" className="mr-1">
                      {row.red_flag_count} red
                    </Badge>
                  )}
                  {row.warning_count > 0 && (
                    <Badge variant="secondary">{row.warning_count} warn</Badge>
                  )}
                  {row.red_flag_count === 0 && row.warning_count === 0 && "—"}
                </TableCell>
                <TableCell>
                  <Badge
                    variant={row.report_status === "finalized" ? "default" : "secondary"}
                  >
                    {row.report_status}
                  </Badge>
                </TableCell>
                <TableCell>
                  <Button
                    render={<Link href={`/admin/sessions/${row.session_id}`} />}
                    size="sm"
                    variant="outline"
                  >
                    Report
                  </Button>
                </TableCell>
              </TableRow>
            ))}
            {data && data.items.length === 0 && (
              <TableRow>
                <TableCell colSpan={8} className="text-center text-muted-foreground py-8">
                  No completed sessions yet.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
