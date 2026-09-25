/**
 * Small wrapper around fetch for calling the SGJio API.
 *
 * Both apps call relative paths such as "/api/auth/me". In development Vite forwards
 * /api to the FastAPI server, so cookies are sent automatically.
 */

export class ApiError extends Error {
  /** HTTP status, or 0 if the server could not be reached. */
  readonly status: number;
  /** Machine-readable code from the API, e.g. "invalid_credentials". */
  readonly code: string;
  /** Field name -> message, from the API's validation errors (HTTP 422). */
  readonly fieldErrors: Record<string, string>;
  /** Set when sign-in is temporarily blocked (HTTP 429). */
  readonly blockedUntil?: Date;

  constructor(
    status: number,
    code: string,
    message: string,
    extra: { fieldErrors?: Record<string, string>; blockedUntil?: Date } = {},
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.fieldErrors = extra.fieldErrors ?? {};
    this.blockedUntil = extra.blockedUntil;
  }
}

type ApiOptions = {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  signal?: AbortSignal;
};

export async function apiFetch<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const { method = "GET", body, signal } = options;
  let response: Response;
  try {
    response = await fetch(path, {
      method,
      signal,
      credentials: "same-origin",
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError(
      0,
      "network_error",
      "We couldn't reach SGJio. Check your connection and try again.",
    );
  }

  if (response.status === 204) return undefined as T;
  const data: unknown = await response.json().catch(() => null);
  if (!response.ok) throw toApiError(response.status, data);
  return data as T;
}

type ValidationItem = { loc?: Array<string | number>; msg?: string };

function toApiError(status: number, data: unknown): ApiError {
  const detail = (data as { detail?: unknown } | null)?.detail;

  // FastAPI validation errors: a list of { loc: ["body", "email"], msg: "..." }
  if (Array.isArray(detail)) {
    const fieldErrors: Record<string, string> = {};
    for (const item of detail as ValidationItem[]) {
      const field = item.loc?.[item.loc.length - 1];
      if (typeof field === "string" && item.msg) fieldErrors[field] = item.msg;
    }
    return new ApiError(status, "validation_error", "Please check the highlighted fields.", {
      fieldErrors,
    });
  }

  // SGJio errors: { code, message, ...extra }
  if (detail && typeof detail === "object") {
    const { code, message, blocked_until } = detail as {
      code?: string;
      message?: string;
      blocked_until?: string;
    };
    return new ApiError(status, code ?? "error", message ?? "Something went wrong.", {
      blockedUntil: blocked_until ? new Date(blocked_until) : undefined,
    });
  }

  return new ApiError(
    status,
    "error",
    typeof detail === "string" ? detail : "Something went wrong. Please try again.",
  );
}
