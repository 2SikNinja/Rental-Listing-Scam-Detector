"use client";

/**
 * Paste mode form. Collects the listing, sends it to POST /analyze, and
 * shows the result or any errors.
 *
 * This is a Client Component ("use client") because it needs state and
 * event handlers, which only run in the browser.
 *
 * Validation note: the browser checks here (required, maxLength, pattern)
 * are only for a nicer experience. The API validates everything again,
 * because anyone can bypass a browser form and send requests directly.
 */

import { useState, type FormEvent } from "react";

import { analyzeListing, ApiError } from "@/lib/apiClient";
import type { AnalysisResult, FieldError, ListingSubmission } from "@/lib/types";

import PhotoPicker from "./PhotoPicker";
import ResultPanel from "./ResultPanel";

interface FormValues {
  title: string;
  description: string;
  monthlyRent: string;
  bedrooms: string;
  bathrooms: string;
  street: string;
  city: string;
  stateCode: string;
  zipCode: string;
  contactName: string;
  contactEmail: string;
  contactPhone: string;
  sourceUrl: string;
}

const emptyFormValues: FormValues = {
  title: "",
  description: "",
  monthlyRent: "",
  bedrooms: "",
  bathrooms: "",
  street: "",
  city: "",
  stateCode: "",
  zipCode: "",
  contactName: "",
  contactEmail: "",
  contactPhone: "",
  sourceUrl: "",
};

/** Blank inputs become undefined, so they are left out of the JSON entirely. */
function optionalText(rawValue: string): string | undefined {
  const trimmedValue = rawValue.trim();
  return trimmedValue === "" ? undefined : trimmedValue;
}

/** Convert form strings into the exact shape the API expects. */
function buildSubmission(formValues: FormValues): ListingSubmission {
  const bedroomsText = optionalText(formValues.bedrooms);
  return {
    source: "paste",
    title: optionalText(formValues.title),
    description: formValues.description.trim(),
    monthlyRent: optionalText(formValues.monthlyRent.replace(/[$,]/g, "")),
    bedrooms: bedroomsText === undefined ? undefined : Number(bedroomsText),
    bathrooms: optionalText(formValues.bathrooms),
    address: {
      street: optionalText(formValues.street),
      city: optionalText(formValues.city),
      stateCode: optionalText(formValues.stateCode),
      zipCode: optionalText(formValues.zipCode),
    },
    contact: {
      name: optionalText(formValues.contactName),
      email: optionalText(formValues.contactEmail),
      phone: optionalText(formValues.contactPhone),
    },
    sourceUrl: optionalText(formValues.sourceUrl),
  };
}

const inputClassName =
  "w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm outline-none focus:border-zinc-900 focus:ring-2 focus:ring-zinc-900/10 dark:border-zinc-700 dark:bg-zinc-950 dark:focus:border-zinc-100";
const labelClassName = "mb-1 block text-sm font-medium";

export default function ListingForm() {
  const [formValues, setFormValues] = useState<FormValues>(emptyFormValues);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<FieldError[]>([]);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [photos, setPhotos] = useState<File[]>([]);

  function updateField(fieldName: keyof FormValues, newValue: string) {
    setFormValues((previousValues) => ({ ...previousValues, [fieldName]: newValue }));
  }

  async function handleSubmit(submitEvent: FormEvent<HTMLFormElement>) {
    submitEvent.preventDefault();
    setIsSubmitting(true);
    setErrorMessage(null);
    setFieldErrors([]);
    setResult(null);

    try {
      const analysisResult = await analyzeListing(buildSubmission(formValues), photos);
      setResult(analysisResult);
    } catch (caughtError) {
      if (caughtError instanceof ApiError) {
        setErrorMessage(caughtError.message);
        setFieldErrors(caughtError.fieldErrors);
      } else {
        setErrorMessage("Something unexpected went wrong. Please try again.");
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  function handleReset() {
    setFormValues(emptyFormValues);
    setPhotos([]);
    setErrorMessage(null);
    setFieldErrors([]);
    setResult(null);
  }

  return (
    <div className="flex flex-col gap-10">
      <form onSubmit={handleSubmit} className="flex flex-col gap-6" noValidate={false}>
        <fieldset className="flex flex-col gap-4">
          <legend className="mb-2 text-lg font-semibold">Listing</legend>

          <div>
            <label htmlFor="title" className={labelClassName}>Title</label>
            <input id="title" className={inputClassName} maxLength={300}
              value={formValues.title} onChange={(changeEvent) => updateField("title", changeEvent.target.value)}
              placeholder="Sunny 2BR near downtown" />
          </div>

          <div>
            <label htmlFor="description" className={labelClassName}>
              Description <span className="text-red-600">*</span>
            </label>
            <textarea id="description" className={`${inputClassName} min-h-40`} required minLength={20} maxLength={20000}
              value={formValues.description} onChange={(changeEvent) => updateField("description", changeEvent.target.value)}
              placeholder="Paste the full listing text here" />
            <p className="mt-1 text-xs text-zinc-500">{formValues.description.length.toLocaleString()} / 20,000 characters</p>
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div>
              <label htmlFor="monthlyRent" className={labelClassName}>Monthly rent ($)</label>
              <input id="monthlyRent" className={inputClassName} inputMode="decimal"
                value={formValues.monthlyRent} onChange={(changeEvent) => updateField("monthlyRent", changeEvent.target.value)}
                placeholder="2100" />
            </div>
            <div>
              <label htmlFor="bedrooms" className={labelClassName}>Bedrooms</label>
              <input id="bedrooms" type="number" min={0} max={20} step={1} className={inputClassName}
                value={formValues.bedrooms} onChange={(changeEvent) => updateField("bedrooms", changeEvent.target.value)} />
            </div>
            <div>
              <label htmlFor="bathrooms" className={labelClassName}>Bathrooms</label>
              <input id="bathrooms" type="number" min={0} max={20} step={0.5} className={inputClassName}
                value={formValues.bathrooms} onChange={(changeEvent) => updateField("bathrooms", changeEvent.target.value)} />
            </div>
          </div>
        </fieldset>

        <fieldset className="flex flex-col gap-4">
          <legend className="mb-2 text-lg font-semibold">Photos</legend>
          <PhotoPicker photos={photos} onPhotosChange={setPhotos} />
        </fieldset>

        <fieldset className="flex flex-col gap-4">
          <legend className="mb-2 text-lg font-semibold">Address</legend>
          <div>
            <label htmlFor="street" className={labelClassName}>Street</label>
            <input id="street" className={inputClassName} maxLength={300} autoComplete="off"
              value={formValues.street} onChange={(changeEvent) => updateField("street", changeEvent.target.value)} />
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div>
              <label htmlFor="city" className={labelClassName}>City</label>
              <input id="city" className={inputClassName} maxLength={100} autoComplete="off"
                value={formValues.city} onChange={(changeEvent) => updateField("city", changeEvent.target.value)} />
            </div>
            <div>
              <label htmlFor="stateCode" className={labelClassName}>State</label>
              <input id="stateCode" className={inputClassName} maxLength={2} pattern="[A-Za-z]{2}" autoComplete="off"
                value={formValues.stateCode} onChange={(changeEvent) => updateField("stateCode", changeEvent.target.value)}
                placeholder="CA" />
            </div>
            <div>
              <label htmlFor="zipCode" className={labelClassName}>ZIP code</label>
              <input id="zipCode" className={inputClassName} maxLength={5} pattern="[0-9]{5}" inputMode="numeric" autoComplete="off"
                value={formValues.zipCode} onChange={(changeEvent) => updateField("zipCode", changeEvent.target.value)}
                placeholder="91101" />
            </div>
          </div>
        </fieldset>

        <fieldset className="flex flex-col gap-4">
          <legend className="mb-2 text-lg font-semibold">Contact info from the listing</legend>
          <p className="-mt-2 text-xs text-zinc-500">
            Emails and phone numbers are stored only as one-way hashes, never as plain text.
          </p>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div>
              <label htmlFor="contactName" className={labelClassName}>Name</label>
              <input id="contactName" className={inputClassName} maxLength={100} autoComplete="off"
                value={formValues.contactName} onChange={(changeEvent) => updateField("contactName", changeEvent.target.value)} />
            </div>
            <div>
              <label htmlFor="contactEmail" className={labelClassName}>Email</label>
              <input id="contactEmail" type="email" className={inputClassName} maxLength={254} autoComplete="off"
                value={formValues.contactEmail} onChange={(changeEvent) => updateField("contactEmail", changeEvent.target.value)} />
            </div>
            <div>
              <label htmlFor="contactPhone" className={labelClassName}>Phone</label>
              <input id="contactPhone" type="tel" className={inputClassName} maxLength={30} autoComplete="off"
                value={formValues.contactPhone} onChange={(changeEvent) => updateField("contactPhone", changeEvent.target.value)} />
            </div>
          </div>
          <div>
            <label htmlFor="sourceUrl" className={labelClassName}>Listing link (optional)</label>
            <input id="sourceUrl" type="url" className={inputClassName} maxLength={2048}
              value={formValues.sourceUrl} onChange={(changeEvent) => updateField("sourceUrl", changeEvent.target.value)}
              placeholder="https://..." />
            <p className="mt-1 text-xs text-zinc-500">Only the website name is kept, not the full link.</p>
          </div>
        </fieldset>

        {errorMessage && (
          <div role="alert" className="rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-900 dark:border-red-800 dark:bg-red-950 dark:text-red-100">
            <p className="font-medium">{errorMessage}</p>
            {fieldErrors.length > 0 && (
              <ul className="mt-2 list-disc pl-5">
                {fieldErrors.map((fieldError) => (
                  <li key={`${fieldError.field}-${fieldError.message}`}>
                    <span className="font-mono">{fieldError.field}</span>: {fieldError.message}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        <div className="flex gap-3">
          <button type="submit" disabled={isSubmitting}
            className="rounded-lg bg-zinc-900 px-5 py-2.5 text-sm font-medium text-white transition hover:bg-zinc-700 disabled:cursor-not-allowed disabled:opacity-60 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300">
            {isSubmitting ? "Analyzing..." : "Analyze listing"}
          </button>
          <button type="button" onClick={handleReset}
            className="rounded-lg border border-zinc-300 px-5 py-2.5 text-sm font-medium transition hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-900">
            Clear
          </button>
        </div>
      </form>

      {result && <ResultPanel result={result} />}
    </div>
  );
}
