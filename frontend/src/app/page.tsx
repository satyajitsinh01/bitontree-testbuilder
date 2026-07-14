import Link from "next/link";
import { Button } from "@/components/ui/button";
import { ClipboardList } from "lucide-react";

export default function Home() {
  return (
    <main className="min-h-screen flex items-center justify-center bg-gradient-to-br from-muted/60 via-background to-accent/40 p-6">
      <div className="max-w-md w-full text-center space-y-6">
        <span className="inline-flex h-14 w-14 items-center justify-center rounded-2xl bg-primary text-primary-foreground shadow-lg shadow-primary/15">
          <ClipboardList className="h-7 w-7" />
        </span>
        <div className="space-y-2">
          <h1 className="text-4xl font-bold tracking-tight">TestBuilder</h1>
          <p className="text-muted-foreground">
            Build proctored assessments, invite candidates, and evaluate with AI
            assistance — one sign-in for admins and candidates.
          </p>
        </div>
        <Button render={<Link href="/login" />} size="lg" className="px-10">
          Sign in
        </Button>
      </div>
    </main>
  );
}
