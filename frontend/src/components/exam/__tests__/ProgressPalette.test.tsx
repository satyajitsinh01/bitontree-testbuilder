import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ProgressPalette } from "../ProgressPalette";
import type { ExamQuestion } from "@/lib/types";

function makeQuestion(id: string, state: ExamQuestion["state"]): ExamQuestion {
  return {
    session_question_id: id,
    section_id: "s1",
    order_index: 0,
    qtype: "mcq",
    answer_type: "single_choice",
    title: id,
    body: "",
    config: {},
    points: 1,
    state,
    saved_answer: null,
  };
}

describe("ProgressPalette (UT-M6-03 / FR-054)", () => {
  const questions = [
    makeQuestion("q1", "answered"),
    makeQuestion("q2", "unseen"),
    makeQuestion("q3", "marked_review"),
    makeQuestion("q4", "seen"),
  ];

  it("shows attempted / unattempted / marked counts", () => {
    render(<ProgressPalette questions={questions} currentIndex={0} onJump={() => {}} />);
    expect(screen.getByTestId("count-attempted")).toHaveTextContent("Attempted: 1");
    expect(screen.getByTestId("count-unattempted")).toHaveTextContent("Unattempted: 2");
    expect(screen.getByTestId("count-marked")).toHaveTextContent("Marked for review: 1");
  });

  it("jumps to a question when its number is clicked", async () => {
    const onJump = jest.fn();
    render(<ProgressPalette questions={questions} currentIndex={0} onJump={onJump} />);
    await userEvent.click(screen.getByRole("button", { name: /Question 3/ }));
    expect(onJump).toHaveBeenCalledWith(2);
  });

  it("labels each question button with its state for assistive tech", () => {
    render(<ProgressPalette questions={questions} currentIndex={1} onJump={() => {}} />);
    expect(
      screen.getByRole("button", { name: "Question 3: marked_review" })
    ).toBeInTheDocument();
  });
});
