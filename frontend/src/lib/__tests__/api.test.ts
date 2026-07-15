import { api, ApiError, errorText, setRefreshToken, setToken } from "../api";

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

describe("candidate token refresh", () => {
  beforeEach(() => {
    window.localStorage.clear();
    jest.restoreAllMocks();
  });

  afterEach(() => {
    delete (global as { fetch?: typeof fetch }).fetch;
  });

  it("rotates an expired candidate token and retries the request", async () => {
    setToken("candidate", "expired-access");
    setRefreshToken("candidate", "refresh-one");
    const fetchMock = jest
      .fn()
      .mockResolvedValueOnce({ status: 401 } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          data: { access_token: "fresh-access", refresh_token: "refresh-two" },
        }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: { get: () => "application/json" },
        json: async () => ({ data: { status: "auto_submitted" }, error: null }),
      } as unknown as Response);
    (global as { fetch?: typeof fetch }).fetch = fetchMock;

    const result = await api<{ status: string }>("/exam/state", {
      token: "candidate",
    });

    expect(result.status).toBe("auto_submitted");
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(window.localStorage.getItem("tb_candidate_token")).toBe("fresh-access");
    expect(window.localStorage.getItem("tb_candidate_refresh_token")).toBe("refresh-two");
  });
});
