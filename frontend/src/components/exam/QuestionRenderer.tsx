"use client";

import type { ExamQuestion } from "@/lib/types";
import { Textarea } from "@/components/ui/textarea";
import { CodingWorkspace } from "@/components/exam/CodingWorkspace";

export function QuestionRenderer({
  question,
  answer,
  onChange,
}: {
  question: ExamQuestion;
  answer: Record<string, unknown>;
  onChange: (payload: Record<string, unknown>) => void;
}) {
  if (question.qtype === "mcq") {
    const selected = (answer.selected_option_ids as string[]) ?? [];
    const multi = question.answer_type === "multi_choice";
    return (
      <div className="space-y-2">
        {(question.config.options ?? []).map((option) => {
          const checked = selected.includes(option.id);
          return (
            <label
              key={option.id}
              className="flex items-center gap-3 rounded-md border p-3 text-sm cursor-pointer hover:bg-muted has-[:checked]:border-primary has-[:checked]:bg-primary/5"
            >
              <input
                type={multi ? "checkbox" : "radio"}
                name={question.session_question_id}
                checked={checked}
                onChange={() => {
                  const next = multi
                    ? checked
                      ? selected.filter((id) => id !== option.id)
                      : [...selected, option.id]
                    : [option.id];
                  onChange({ selected_option_ids: next });
                }}
              />
              {option.text}
            </label>
          );
        })}
      </div>
    );
  }

  if (question.qtype === "text") {
    return (
      <Textarea
        rows={8}
        placeholder="Type your answer…"
        value={(answer.text as string) ?? ""}
        onChange={(e) => onChange({ text: e.target.value })}
      />
    );
  }

  return <CodingWorkspace question={question} answer={answer} onChange={onChange} />;
}
