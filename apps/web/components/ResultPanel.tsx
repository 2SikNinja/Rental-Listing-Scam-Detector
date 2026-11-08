/**
 * Displays an analysis result: risk level, each red flag with its
 * explanation, which checks ran, safety tips, and the disclaimer.
 *
 * Explainability is the point: every signal shows *why* it was raised.
 */

import type { AnalysisResult, RiskLevel, Severity } from "@/lib/types";

const riskStyles: Record<RiskLevel, { label: string; summary: string; className: string }> = {
  low: {
    label: "Low risk",
    summary: "The checks that ran found few or no common scam warning signs.",
    className: "border-emerald-300 bg-emerald-50 text-emerald-900 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-100",
  },
  medium: {
    label: "Medium risk",
    summary: "This listing shows some warning signs. Verify the landlord and the unit before paying anything.",
    className: "border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-100",
  },
  high: {
    label: "High risk",
    summary: "This listing shares several patterns with known rental scams. Do not send money until you have verified everything.",
    className: "border-red-300 bg-red-50 text-red-900 dark:border-red-800 dark:bg-red-950 dark:text-red-100",
  },
  insufficient_data: {
    label: "Not enough information",
    summary: "No red flags were found, but too few checks could run to call this listing low risk. Add the missing details below for a fuller check.",
    className: "border-zinc-300 bg-zinc-100 text-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100",
  },
};

const severityBadge: Record<Severity, string> = {
  info: "bg-zinc-200 text-zinc-800 dark:bg-zinc-800 dark:text-zinc-200",
  low: "bg-sky-100 text-sky-900 dark:bg-sky-950 dark:text-sky-200",
  medium: "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200",
  high: "bg-red-100 text-red-900 dark:bg-red-950 dark:text-red-200",
};

/** Text check evidence: the exact phrases that triggered a signal. */
function getMatchedPhrases(evidence: Record<string, unknown>): string[] {
  const matchedPhrases = evidence.matchedPhrases;
  return Array.isArray(matchedPhrases) ? matchedPhrases.filter((phrase) => typeof phrase === "string") : [];
}

export default function ResultPanel({ result }: { result: AnalysisResult }) {
  const riskStyle = riskStyles[result.riskLevel];
  const noChecksRan = result.checksRun.length === 0;

  return (
    <section aria-live="polite" className="flex flex-col gap-6">
      <div className={`rounded-xl border p-5 ${riskStyle.className}`}>
        <p className="text-sm font-medium uppercase tracking-wide opacity-80">Assessment</p>
        <p className="mt-1 text-2xl font-semibold">{riskStyle.label}</p>
        <p className="mt-2 text-sm">{riskStyle.summary}</p>
        <p className="mt-3 text-xs opacity-80">
          {result.totalPoints} risk points
          {result.riskThresholds.medium !== undefined && result.riskThresholds.high !== undefined && (
            <> (medium starts at {result.riskThresholds.medium}, high at {result.riskThresholds.high})</>
          )}
        </p>
      </div>

      {noChecksRan && (
        <p className="rounded-lg border border-zinc-300 bg-zinc-100 p-4 text-sm text-zinc-700 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300">
          No detection checks ran on this listing yet, so this result does not reflect any analysis.
        </p>
      )}

      <div>
        <h2 className="text-lg font-semibold">Red flags</h2>
        {result.signals.length === 0 ? (
          <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">No red flags were found by the checks that ran.</p>
        ) : (
          <ul className="mt-3 flex flex-col gap-3">
            {result.signals.map((signal) => (
              <li key={signal.signalCode} className="rounded-lg border border-zinc-200 p-4 dark:border-zinc-800">
                <div className="flex items-center gap-2">
                  <span className={`rounded px-2 py-0.5 text-xs font-medium ${severityBadge[signal.severity]}`}>
                    {signal.severity}
                  </span>
                  <span className="text-xs uppercase tracking-wide text-zinc-500">{signal.checkName} check</span>
                  <span className="ml-auto text-xs text-zinc-500">
                    {signal.points === 0 && signal.severity !== "info"
                      ? `+0 pts (${signal.checkName} check's point limit already reached)`
                      : `+${signal.points} pts`}
                  </span>
                </div>
                <p className="mt-2 text-sm">{signal.explanation}</p>
                {getMatchedPhrases(signal.evidence).length > 0 && (
                  <p className="mt-2 text-xs text-zinc-600 dark:text-zinc-400">
                    Found in listing:{" "}
                    {getMatchedPhrases(signal.evidence).map((phrase, phraseIndex) => (
                      <span key={phrase}>
                        {phraseIndex > 0 && ", "}
                        <q className="font-mono">{phrase}</q>
                      </span>
                    ))}
                  </p>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="text-sm text-zinc-600 dark:text-zinc-400">
        <p>
          <span className="font-medium text-zinc-800 dark:text-zinc-200">Checks run:</span>{" "}
          {result.checksRun.length > 0 ? result.checksRun.join(", ") : "none"}
        </p>
        <p>
          <span className="font-medium text-zinc-800 dark:text-zinc-200">Not checked:</span>{" "}
          {result.checksSkipped.length > 0 ? result.checksSkipped.join(", ") : "none"}
        </p>
        {Object.entries(result.skipReasons ?? {}).length > 0 && (
          <ul className="mt-2 list-disc pl-5 text-xs">
            {Object.entries(result.skipReasons ?? {}).map(([checkName, skipReason]) => (
              <li key={checkName}>
                <span className="font-medium">{checkName}</span>: {skipReason}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div>
        <h2 className="text-lg font-semibold">Safety tips</h2>
        <ul className="mt-2 list-disc pl-5 text-sm leading-6">
          {result.safetyTips.map((tip) => (
            <li key={tip}>{tip}</li>
          ))}
        </ul>
      </div>

      <p className="border-t border-zinc-200 pt-4 text-xs leading-5 text-zinc-500 dark:border-zinc-800">
        {result.disclaimer}
        {result.scoringConfigVersion && <> Scoring version {result.scoringConfigVersion}.</>}
      </p>
    </section>
  );
}
