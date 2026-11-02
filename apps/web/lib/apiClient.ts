/**
 * The only place the web app talks to the FastAPI backend.
 *
 * Keeping every API call in one file means the base URL, timeout, and
 * error handling live in one spot. The Chrome extension will later use
 * the same request format.
 */

import type { AnalysisResult, FieldError, ListingSubmission } from "./types";

// NEXT_PUBLIC_ values are built into the browser bundle, so this must
// only ever be a public URL. No secrets belong here.
const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

const requestTimeoutMs = 30_000;

/** Thrown for any failed request, with a message safe to show the user. */
export class ApiError extends Error {
  readonly fieldErrors: FieldError[];

  constructor(message: string, fieldErrors: FieldError[] = []) {
    super(message);
    this.name = "ApiError";
    this.fieldErrors = fieldErrors;
  }
}

interface FastApiValidationItem {
  loc: (string | number)[];
  msg: string;
}

/**
 * Turn FastAPI's 422 body into simple { field, message } pairs.
 * Example loc: ["body", "address", "zipCode"]  ->  field "address.zipCode"
 */
function parseValidationErrors(responseBody: unknown): FieldError[] {
  const detail = (responseBody as { detail?: unknown })?.detail;
  if (!Array.isArray(detail)) {
    return [];
  }
  return (detail as FastApiValidationItem[]).map((item) => ({
    field: item.loc.filter((part) => part !== "body").join("."),
    message: item.msg.replace(/^Value error, /, ""),
  }));
}

export async function analyzeListing(submission: ListingSubmission): Promise<AnalysisResult> {
  const abortController = new AbortController();
  const timeoutId = setTimeout(() => abortController.abort(), requestTimeoutMs);

  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl}/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(submission),
      signal: abortController.signal,
    });
  } catch (networkError) {
    if ((networkError as Error).name === "AbortError") {
      throw new ApiError("The analysis took too long. Please try again.");
    }
    throw new ApiError(
      "Could not reach the analysis server. Check that the API is running and try again.",
    );
  } finally {
    clearTimeout(timeoutId);
  }

  if (response.status === 422) {
    const responseBody = await response.json().catch(() => null);
    throw new ApiError("Some fields need fixing.", parseValidationErrors(responseBody));
  }

  if (response.status === 429) {
    throw new ApiError("Too many requests. Please wait a minute and try again.");
  }

  if (!response.ok) {
    throw new ApiError(`The server had a problem (error ${response.status}). Please try again.`);
  }

  return (await response.json()) as AnalysisResult;
}
