import { ApiError, errorText } from "../api";

describe("errorText", () => {
  it("renders the message for a simple ApiError", () => {
    expect(errorText(new ApiError(409, "duplicate_email_in_assessment"))).toBe(
      "duplicate_email_in_assessment"
    );
  });

  it("joins string detail lists (publish validation errors)", () => {
    const error = new ApiError(422, "publish_failed", "publish_failed", [
      "section weightages must sum to 100",
      "section 'DSA': duration must be > 0",
    ]);
    expect(errorText(error)).toContain("sum to 100");
    expect(errorText(error)).toContain("duration must be > 0");
  });

  it("stringifies non-string details", () => {
    const error = new ApiError(422, "validation_error", "validation_error", [
      { loc: ["body", "email"], msg: "invalid" },
    ]);
    expect(errorText(error)).toContain("email");
  });

  it("falls back for plain errors", () => {
    expect(errorText(new Error("boom"))).toBe("boom");
    expect(errorText("weird")).toBe("weird");
  });
});
