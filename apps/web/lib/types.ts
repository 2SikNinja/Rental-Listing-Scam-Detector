/**
 * TypeScript types that mirror the FastAPI schemas in
 * apps/api/app/schemas/listing.py.
 *
 * Keeping these in sync means TypeScript catches mistakes (like a
 * misspelled field) before the request ever reaches the API.
 */

export type CheckName = "price" | "text" | "photo" | "address" | "contact";
export type Severity = "info" | "low" | "medium" | "high";
export type RiskLevel = "low" | "medium" | "high";

export interface AddressInput {
  street?: string;
  city?: string;
  stateCode?: string;
  zipCode?: string;
}

export interface ContactInput {
  name?: string;
  email?: string;
  phone?: string;
}

export interface ListingSubmission {
  source: "paste";
  title?: string;
  description: string;
  monthlyRent?: string;
  bedrooms?: number;
  bathrooms?: string;
  address: AddressInput;
  contact: ContactInput;
  sourceUrl?: string;
}

export interface Signal {
  checkName: CheckName;
  signalCode: string;
  severity: Severity;
  points: number;
  explanation: string;
  evidence: Record<string, unknown>;
}

export interface AnalysisResult {
  analysisId: string;
  riskLevel: RiskLevel;
  totalPoints: number;
  signals: Signal[];
  checksRun: CheckName[];
  checksSkipped: CheckName[];
  safetyTips: string[];
  disclaimer: string;
}

/** One field-level error, simplified from FastAPI's 422 response. */
export interface FieldError {
  field: string;
  message: string;
}
