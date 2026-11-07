# Detector Evaluation

How well does the detector separate rental scams from honest listings? This folder holds a small labeled dataset, the script that scores it, and the results.

## Headline result

On the **held-out test split** (never used while tuning):

| | Before tuning | After tuning |
|---|---|---|
| Scams caught (recall) | 5 of 8 (62%) | **7 of 8 (88%)**, 95% CI 53% to 98% |
| Flags that were real scams (precision) | 71% | **78%**, 95% CI 45% to 94% |
| Honest listings flagged | 2 of 11 | **2 of 11** (no increase) |

A listing counts as "flagged" when the result is **Medium or High**.

The confidence intervals are wide on purpose: with 19 test listings, one listing moves a rate by 5 to 13 points. These numbers show the detector is doing something real, not that it is 88% accurate in the wild.

## Dataset

[`labeledListings.csv`](labeledListings.csv): 37 listings, split roughly in half.

| | Dev (for tuning) | Test (held out) | Total |
|---|---|---|---|
| Scams | 7 | 8 | 15 |
| Legitimate | 11 | 11 | 22 |

**Scam listings** are reconstructed from 15 distinct, cited reports: 2025 to 2026 news stories and police warnings (ABC7, ABC11, CBS Miami, KAKE, SF Standard, BBB warnings, and others), plus two older scam forum posts. Each row links its source. Listing text paraphrases only details in the report, with no real names, phone numbers, or emails. Where a report names a city but not a ZIP code, a ZIP in that city is used and the row says so. Where no rent was reported, rent is left blank, so the price check honestly can't run.

**Legitimate listings** are synthetic, written to resemble ordinary listings across 20 U.S. cities, because copying real listings would break listing sites' terms. They deliberately include **hard cases**:

| ID | Why it's hard |
|---|---|
| legit-03 | Owner accepts Zelle for rent after the lease is signed |
| legit-05 | Anti-scam warning that names wire transfers, gift cards, and Zelle |
| legit-06 | Occupied unit, showings only with 24 hours notice |
| legit-12 | Legitimate holding deposit after approval |
| legit-13 | Room in a shared house (priced like a room, compared against 1-bedroom rents) |
| legit-14 | Small backyard studio priced well below a typical studio |
| legit-15 | Owner relocating overseas, with a property manager handling showings |
| legit-21 | Owner asks people to text to schedule |

## Method

1. **Dev/test split before any tuning.** Rules and weights were changed only by looking at dev results. The test split was run once at the end. Cases I had already seen while writing the original rules (the October 2026 news cases and the forum posts) were placed in dev.
2. **Same pipeline as production.** [`evaluateDetector.py`](../apps/api/scripts/evaluateDetector.py) calls the API's own `runAnalysis` with the real HUD rent data and the real `weights.yaml`.
3. **Offline.** Address lookups, photo matching, and cross-listing reuse need live services or a history of earlier listings, so they are skipped. These results cover the price, text, and throwaway-email checks.
4. **Uncertainty.** Every rate has a 95% Wilson confidence interval ([`metrics.py`](../apps/api/app/evaluation/metrics.py)).

Run it from `apps/api`:

```bash
uv run python scripts/evaluateDetector.py --split dev    # while tuning
uv run python scripts/evaluateDetector.py --split test   # final check only
```

## What the baseline revealed, and what changed

The original rules were written around classic scam wording ("I'm a missionary overseas, keys will be mailed"). The dev baseline caught only **3 of 7** scams. All four 2025 to 2026 social media scams scored 0 or 10 points. Changes, all based on dev results:

- **Payment requests in modern wording:** "deposit to hold it," "take the house off the market," "remain on the market until funds are received"
- **More payment channels:** Chime, Apple Pay, international money transfer services, and plural "wire transfers" (a bug: the singular-only pattern never matched "transfers")
- **Remote owner excuses:** "I live in another state so I can't meet," "can't meet you in person"
- **Keys mailed** with words in between ("the keys and lease papers will be shipped")
- **Negated lists:** "We will never ask for wire transfers, gift cards or Zelle" was wrongly flagged because negation only looked 4 words back

I intentionally did not add a rule for the one remaining dev miss (staged fees with no other warning sign), to avoid fitting the rules to every dev example.

## Which signals matter

Across all 37 listings:

| Signal | Scams (of 15) | Legitimate (of 22) |
|---|---|---|
| Payment before viewing | 9 | 1 |
| Peer-to-peer payment app | 7 | 1 |
| Owner unavailable | 4 | 0 |
| Can't show the unit | 3 | 0 |
| Untraceable payment | 3 | 0 |
| Rent far below market | 2 | 1 |
| Keys mailed | 2 | 0 |

**Asking for money before a viewing or lease is the strongest signal in modern scams.** The price check fired less than expected, but mostly because news reports rarely include the rent and ZIP code, not because the check failed.

## Remaining errors

| ID | Error | Why |
|---|---|---|
| scam-04 | Missed | Staged fees ("$80 application fee, then $300 and $700") with no other wording signal |
| scam-12 | Missed | A one-sentence ad. The only signal is a payment app, which honest landlords use too |
| legit-12 | False alarm | A legitimate holding deposit after approval matches the "holding deposit" rule |
| legit-13 | False alarm | A room in a shared house compared against 1-bedroom market rent |
| legit-14 | False alarm | A small backyard studio priced like what it is, compared against regular studios |

## Limitations

- **Small sample.** 37 listings, wide intervals. Treat the numbers as directional.
- **Reconstruction bias.** Scam listings were rewritten from news summaries by the same person who wrote the detection rules, which can make scams look more "textbook" than real ads. Synthetic legitimate listings have the same risk in reverse. Real, unedited listings would be a stronger test.
- **Selection bias.** Scams that make the news are the ones that got noticed. Quieter scams may look different.
- **Offline only.** Address, photo, and cross-listing checks aren't measured here.
- **One rule is known to be imperfect.** The holding-deposit false positive is kept as a documented test case rather than hidden.

## Guardrail

[`test_evaluationRegression.py`](../apps/api/tests/test_evaluationRegression.py) runs this evaluation in CI on every push. If a change drops below 12 of 15 scams caught, or rises above 4 false alarms, the build fails.

## Next steps

1. Add real, recent listings: copy text from posts on r/Scams, BBB Scam Tracker reports, and real legitimate listings (by hand, not scraping), then re-split.
2. Detect "room in a shared house" so rooms aren't compared against whole-unit rents.
3. Distinguish a holding deposit **after approval** from one requested before viewing.
