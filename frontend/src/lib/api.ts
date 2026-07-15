const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type TokenKind = "admin" | "candidate";

export class ApiError extends Error {
  code: string;
  status: number;
  details?: unknown;
  payload: Record<string, unknown>;
  constructor(
    status: number,
    code: string,
    message?: string,
    details?: unknown,
    payload: Record<string, unknown> = {}
  ) {
    super(message ?? code);
    this.status = status;
    this.code = code;
    this.details = details;
    this.payload = payload;
  }
}

export function getToken(kind: TokenKind): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(`tb_${kind}_token`);
}

export function setToken(kind: TokenKind, token: string | null) {
  if (token === null) window.localStorage.removeItem(`tb_${kind}_token`);
  else window.localStorage.setItem(`tb_${kind}_token`, token);
}

export function setRefreshToken(kind: TokenKind, token: string | null) {
  if (typeof window === "undefined") return;
  if (token === null) window.localStorage.removeItem(`tb_${kind}_refresh_token`);
  else window.localStorage.setItem(`tb_${kind}_refresh_token`, token);
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  token?: TokenKind;
  formData?: FormData;
}

interface ErrorPayload {
  code?: string;
  message?: string;
  details?: unknown;
}

let candidateRefresh: Promise<boolean> | null = null;

async function refreshCandidateToken(): Promise<boolean> {
  if (typeof window === "undefined") return false;
  const refreshToken = window.localStorage.getItem("tb_candidate_refresh_token");
  if (!refreshToken) return false;
  if (!candidateRefresh) {
    candidateRefresh = (async () => {
      const response = await fetch(`${API_BASE}/api/v1/auth/candidate/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
      if (!response.ok) return false;
      const payload = (await response.json()) as {
        data?: { access_token?: string; refresh_token?: string };
      };
      if (!payload.data?.access_token || !payload.data.refresh_token) return false;
      setToken("candidate", payload.data.access_token);
      setRefreshToken("candidate", payload.data.refresh_token);
      return true;
    })()
      .catch(() => false)
      .finally(() => {
        candidateRefresh = null;
      });
  }
  return candidateRefresh;
}

export async function api<T>(
  path: string,
  options: RequestOptions = {},
  hasRetried = false
): Promise<T> {
  const headers: Record<string, string> = {};
  if (options.token) {
    const token = getToken(options.token);
    if (token) headers.Authorization = `Bearer ${token}`;
  }
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  const response = await fetch(`${API_BASE}/api/v1${path}`, {
    method: options.method ?? (options.body !== undefined || options.formData ? "POST" : "GET"),
    headers,
    body: options.formData ?? (options.body !== undefined ? JSON.stringify(options.body) : undefined),
  });
  if (
    response.status === 401 &&
    options.token === "candidate" &&
    !hasRetried &&
    !path.startsWith("/auth/candidate/refresh") &&
    (await refreshCandidateToken())
  ) {
    return api<T>(path, options, true);
  }
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    if (!response.ok) throw new ApiError(response.status, "http_error");
    return (await response.text()) as unknown as T;
  }
  const payload = (await response.json()) as { data: T; error: ErrorPayload | null };
  if (!response.ok || payload.error) {
    const err = payload.error ?? {};
    throw new ApiError(
      response.status,
      err.code ?? "unknown_error",
      err.message,
      err.details,
      err as Record<string, unknown>
    );
  }
  return payload.data;
}

export function errorText(error: unknown): string {
  if (error instanceof ApiError) {
    if (Array.isArray(error.details)) {
      const parts = error.details.map((d) =>
        typeof d === "string" ? d : JSON.stringify(d)
      );
      return `${error.message}: ${parts.join("; ")}`;
    }
    return error.message;
  }
  return error instanceof Error ? error.message : String(error);
}
