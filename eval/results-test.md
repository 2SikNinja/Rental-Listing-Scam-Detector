# Evaluation results: test split

Scoring config `2026-11-07.3`. 19 listings: 8 scams, 11 legitimate.
"Flagged" means a Medium or High result. Offline run: address, photo, and cross-listing checks are skipped.

## Confusion matrix

| | Flagged | Not flagged |
|---|---|---|
| **Scam** | 7 (caught) | 1 (missed) |
| **Legitimate** | 2 (false alarm) | 9 (correctly passed) |

## Metrics (with 95% confidence intervals)

| Metric | Value | 95% interval |
|---|---|---|
| Recall (scams caught) | 88% | 53% to 98% |
| Precision (flags that were scams) | 78% | 45% to 94% |
| False alarm rate (honest listings flagged) | 18% | 5% to 48% |
| F1 | 82% | |

## Risk levels by label

| Label | High | Medium | Low | Not enough info |
|---|---|---|---|---|
| scam | 3 | 4 | 0 | 1 |
| legit | 0 | 2 | 0 | 9 |

## How often each signal fires

| Signal | Scams (of 8) | Legitimate (of 11) |
|---|---|---|
| `CANNOT_SHOW_UNIT` | 1 | 0 |
| `OWNER_UNAVAILABLE` | 1 | 0 |
| `PAYMENT_BEFORE_VIEWING` | 7 | 1 |
| `PEER_TO_PEER_PAYMENT` | 5 | 0 |
| `PERSONAL_INFO_REQUEST` | 1 | 0 |
| `RENT_BELOW_MARKET` | 0 | 1 |
| `UNTRACEABLE_PAYMENT` | 1 | 0 |

## Threshold sweep

| Flag at points >= | Precision | Recall | False alarms |
|---|---|---|---|
| 5 | 80% | 100% | 2 of 11 |
| 10 | 80% | 100% | 2 of 11 |
| 15 | 78% | 88% | 2 of 11 |
| 20 | 78% | 88% | 2 of 11 |
| 25 | 88% | 88% | 1 of 11 |
| 30 | 88% | 88% | 1 of 11 |
| 35 | 100% | 75% | 0 of 11 |
| 40 | 100% | 75% | 0 of 11 |
| 50 | 100% | 38% | 0 of 11 |
| 65 | 100% | 25% | 0 of 11 |

## Every listing

| ID | Label | Result | Points | Signals |
|---|---|---|---|---|
| scam-07 | scam | medium | 45 | PAYMENT_BEFORE_VIEWING, PERSONAL_INFO_REQUEST |
| scam-08 | scam | high | 60 | PAYMENT_BEFORE_VIEWING, UNTRACEABLE_PAYMENT |
| scam-09 | scam | high | 65 | CANNOT_SHOW_UNIT, PAYMENT_BEFORE_VIEWING, PEER_TO_PEER_PAYMENT |
| scam-10 | scam | medium | 40 | PAYMENT_BEFORE_VIEWING, PEER_TO_PEER_PAYMENT |
| scam-11 | scam | high | 65 | OWNER_UNAVAILABLE, PAYMENT_BEFORE_VIEWING, PEER_TO_PEER_PAYMENT |
| scam-12 | scam | insufficient_data ❌ | 10 | PEER_TO_PEER_PAYMENT |
| scam-13 | scam | medium | 30 | PAYMENT_BEFORE_VIEWING |
| scam-15 | scam | medium | 40 | PAYMENT_BEFORE_VIEWING, PEER_TO_PEER_PAYMENT |
| legit-02 | legit | insufficient_data | 0 | none |
| legit-04 | legit | insufficient_data | 0 | none |
| legit-06 | legit | insufficient_data | 0 | none |
| legit-08 | legit | insufficient_data | 0 | none |
| legit-10 | legit | insufficient_data | 0 | none |
| legit-12 | legit | medium ❌ | 30 | PAYMENT_BEFORE_VIEWING |
| legit-14 | legit | medium ❌ | 20 | RENT_BELOW_MARKET |
| legit-16 | legit | insufficient_data | 0 | none |
| legit-18 | legit | insufficient_data | 0 | none |
| legit-20 | legit | insufficient_data | 0 | none |
| legit-22 | legit | insufficient_data | 0 | none |
