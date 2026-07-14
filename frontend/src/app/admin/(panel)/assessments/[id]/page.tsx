"use client";

import { use } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { AssessmentOut } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { BuilderTab } from "@/components/admin/BuilderTab";
import { CandidatesTab } from "@/components/admin/CandidatesTab";
import { ResultsTab } from "@/components/admin/ResultsTab";

export default function AssessmentDetail({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const { data: assessment, refetch } = useQuery({
    queryKey: ["assessment", id],
    queryFn: () => api<AssessmentOut>(`/assessments/${id}`, { token: "admin" }),
  });

  if (!assessment) {
    return <p className="text-muted-foreground">Loading…</p>;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">{assessment.title}</h1>
        <Badge variant={assessment.status === "published" ? "default" : "secondary"}>
          {assessment.status}
        </Badge>
        {assessment.version && (
          <Badge variant="outline">
            v{assessment.version.version}
            {assessment.version.frozen ? " (frozen)" : ""}
          </Badge>
        )}
      </div>
      <Tabs defaultValue="builder">
        <TabsList>
          <TabsTrigger value="builder">Test Builder</TabsTrigger>
          <TabsTrigger value="candidates">Candidates</TabsTrigger>
          <TabsTrigger value="results">Results</TabsTrigger>
        </TabsList>
        <TabsContent value="builder" className="mt-4">
          <BuilderTab assessment={assessment} onChanged={() => refetch()} />
        </TabsContent>
        <TabsContent value="candidates" className="mt-4">
          <CandidatesTab assessmentId={assessment.id} published={assessment.status === "published"} />
        </TabsContent>
        <TabsContent value="results" className="mt-4">
          <ResultsTab assessmentId={assessment.id} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
