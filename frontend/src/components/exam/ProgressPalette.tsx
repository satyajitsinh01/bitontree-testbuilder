"use client";

import type { ExamQuestion } from "@/lib/types";
import { cn } from "@/lib/utils";

const STATE_STYLES: Record<ExamQuestion["state"], string> = {
  unseen: "bg-muted text-muted-foreground",
  seen: "bg-background border",
  answered: "bg-primary text-primary-foreground",
  marked_review: "bg-muted-foreground/80 text-background ring-1 ring-inset ring-foreground/30",
};

/** Question palette with attempted / unattempted / marked counts (FR-054). */
export function ProgressPalette({
  questions,
  currentIndex,
  onJump,
}: {
  questions: ExamQuestion[];
  currentIndex: number;
  onJump: (index: number) => void;
}) {
  const counts = {
    answered: questions.filter((q) => q.state === "answered").length,
    marked: questions.filter((q) => q.state === "marked_review").length,
  };
  const unattempted = questions.length - counts.answered - counts.marked;

  return (
    <div className="space-y-3" data-testid="progress-palette">
      <div className="grid grid-cols-5 gap-2">
        {questions.map((question, index) => (
          <button
            key={question.session_question_id}
            onClick={() => onJump(index)}
            className={cn(
              "h-9 w-9 rounded-md text-sm font-medium transition-all",
              STATE_STYLES[question.state],
              index === currentIndex && "ring-2 ring-primary ring-offset-2"
            )}
            aria-label={`Question ${index + 1}: ${question.state}`}
          >
            {index + 1}
          </button>
        ))}
      </div>
      <div className="space-y-1 text-xs text-muted-foreground">
        <p data-testid="count-attempted">Attempted: {counts.answered}</p>
        <p data-testid="count-unattempted">Unattempted: {unattempted}</p>
        <p data-testid="count-marked">Marked for review: {counts.marked}</p>
      </div>
    </div>
  );
}
