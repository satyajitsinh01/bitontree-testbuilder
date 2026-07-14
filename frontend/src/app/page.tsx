import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ClipboardCheck, ShieldCheck } from "lucide-react";

export default function Home() {
  return (
    <main className="min-h-screen flex items-center justify-center bg-gradient-to-br from-muted/60 via-background to-accent/40 p-6">
      <div className="max-w-3xl w-full space-y-8">
        <div className="text-center space-y-3">
          <span className="inline-flex h-12 w-12 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-lg shadow-primary/20">
            <ClipboardCheck className="h-6 w-6" />
          </span>
          <h1 className="text-4xl font-bold tracking-tight">TestBuilder</h1>
          <p className="text-muted-foreground max-w-lg mx-auto">
            Build proctored assessments, invite candidates, and evaluate with AI assistance.
          </p>
        </div>
        <div className="grid gap-6 sm:grid-cols-2">
          <Card className="transition-shadow hover:shadow-lg hover:shadow-foreground/5">
            <CardHeader>
              <ShieldCheck className="h-8 w-8 text-primary" />
              <CardTitle>Admin Panel</CardTitle>
              <CardDescription>
                Manage tests, questions, candidates, and reports.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Button render={<Link href="/admin/login" />} className="w-full">
                Admin sign in
              </Button>
            </CardContent>
          </Card>
          <Card className="transition-shadow hover:shadow-lg hover:shadow-foreground/5">
            <CardHeader>
              <ClipboardCheck className="h-8 w-8 text-primary" />
              <CardTitle>Candidate</CardTitle>
              <CardDescription>
                Take your assessment with the credentials from your invitation.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Button
                render={<Link href="/candidate/login" />}
                variant="outline"
                className="w-full"
              >
                Candidate sign in
              </Button>
            </CardContent>
          </Card>
        </div>
      </div>
    </main>
  );
}
