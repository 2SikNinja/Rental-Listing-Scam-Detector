# Evaluation results: dev split

Scoring config `2026-11-07.3`. 18 listings: 7 scams, 11 legitimate.
"Flagged" means a Medium or High result. Offline run: address, photo, and cross-listing checks are skipped.

## Confusion matrix

| | Flagged | Not flagged |
|---|---|---|
| **Scam** | 6 (caught) | 1 (missed) |
| **Legitimate** | 1 (false alarm) | 10 (correctly passed) |

## Metrics (with 95% confidence intervals)

| Metric | Value | 95% interval |
|---|---|---|
| Recall (scams caught) | 86% | 49% to 97% |
| Precision (flags that were scams) | 86% | 49% to 97% |
| False alarm rate (honest listings flagged) | 9% | 2% to 38% |
| F1 | 86% | |

## Risk levels by label

| Label | High | Medium | Low | Not enough info |
|---|---|---|---|---|
| scam | 4 | 2 | 0 | 1 |
| legit | 0 | 1 | 3 | 7 |

## How often each signal fires

| Signal | Scams (of 7) | Legitimate (of 11) |
|---|---|---|
| `CANNOT_SHOW_UNIT` | 2 | 0 |
| `KEYS_MAILED` | 2 | 0 |
| `OFF_PLATFORM_CONTACT` | 2 | 1 |
| `OWNER_UNAVAILABLE` | 3 | 0 |
| `PAYMENT_BEFORE_VIEWING` | 2 | 0 |
| `PEER_TO_PEER_PAYMENT` | 2 | 1 |
| `RENT_FAR_BELOW_MARKET` | 2 | 1 |
| `UNTRACEABLE_PAYMENT` | 2 | 0 |

## Threshold sweep

| Flag at points >= | Precision | Recall | False alarms |
|---|---|---|---|
| 5 | 70% | 100% | 3 of 11 |
| 10 | 70% | 100% | 3 of 11 |
| 15 | 78% | 100% | 2 of 11 |
| 20 | 86% | 86% | 1 of 11 |
| 25 | 86% | 86% | 1 of 11 |
| 30 | 83% | 71% | 1 of 11 |
| 35 | 80% | 57% | 1 of 11 |
| 40 | 100% | 57% | 0 of 11 |
| 50 | 100% | 57% | 0 of 11 |
| 65 | 100% | 43% | 0 of 11 |

## Every listing

| ID | Label | Result | Points | Signals |
|---|---|---|---|---|
| scam-01 | scam | high | 75 | RENT_FAR_BELOW_MARKET, OWNER_UNAVAILABLE, PEER_TO_PEER_PAYMENT |
| scam-02 | scam | medium | 30 | PAYMENT_BEFORE_VIEWING |
| scam-03 | scam | high | 60 | PAYMENT_BEFORE_VIEWING, UNTRACEABLE_PAYMENT |
| scam-04 | scam | insufficient_data ❌ | 15 | OFF_PLATFORM_CONTACT |
| scam-05 | scam | high | 100 | RENT_FAR_BELOW_MARKET, OWNER_UNAVAILABLE, CANNOT_SHOW_UNIT, KEYS_MAILED, UNTRACEABLE_PAYMENT |
| scam-06 | scam | high | 65 | OWNER_UNAVAILABLE, CANNOT_SHOW_UNIT, KEYS_MAILED |
| scam-14 | scam | medium | 25 | OFF_PLATFORM_CONTACT, PEER_TO_PEER_PAYMENT |
| legit-01 | legit | low | 0 | none |
| legit-03 | legit | insufficient_data | 10 | PEER_TO_PEER_PAYMENT |
| legit-05 | legit | insufficient_data | 0 | none |
| legit-07 | legit | insufficient_data | 0 | none |
| legit-09 | legit | insufficient_data | 0 | none |
| legit-11 | legit | insufficient_data | 0 | none |
| legit-13 | legit | medium ❌ | 35 | RENT_FAR_BELOW_MARKET |
| legit-15 | legit | insufficient_data | 0 | none |
| legit-17 | legit | insufficient_data | 0 | none |
| legit-19 | legit | low | 0 | none |
| legit-21 | legit | low | 15 | OFF_PLATFORM_CONTACT |
