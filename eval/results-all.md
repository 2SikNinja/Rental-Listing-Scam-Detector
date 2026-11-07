# Evaluation results: all split

Scoring config `2026-11-07.3`. 37 listings: 15 scams, 22 legitimate.
"Flagged" means a Medium or High result. Offline run: address, photo, and cross-listing checks are skipped.

## Confusion matrix

| | Flagged | Not flagged |
|---|---|---|
| **Scam** | 13 (caught) | 2 (missed) |
| **Legitimate** | 3 (false alarm) | 19 (correctly passed) |

## Metrics (with 95% confidence intervals)

| Metric | Value | 95% interval |
|---|---|---|
| Recall (scams caught) | 87% | 62% to 96% |
| Precision (flags that were scams) | 81% | 57% to 93% |
| False alarm rate (honest listings flagged) | 14% | 5% to 33% |
| F1 | 84% | |

## Risk levels by label

| Label | High | Medium | Low | Not enough info |
|---|---|---|---|---|
| scam | 7 | 6 | 0 | 2 |
| legit | 0 | 3 | 3 | 16 |

## How often each signal fires

| Signal | Scams (of 15) | Legitimate (of 22) |
|---|---|---|
| `CANNOT_SHOW_UNIT` | 3 | 0 |
| `KEYS_MAILED` | 2 | 0 |
| `OFF_PLATFORM_CONTACT` | 2 | 1 |
| `OWNER_UNAVAILABLE` | 4 | 0 |
| `PAYMENT_BEFORE_VIEWING` | 9 | 1 |
| `PEER_TO_PEER_PAYMENT` | 7 | 1 |
| `PERSONAL_INFO_REQUEST` | 1 | 0 |
| `RENT_BELOW_MARKET` | 0 | 1 |
| `RENT_FAR_BELOW_MARKET` | 2 | 1 |
| `UNTRACEABLE_PAYMENT` | 3 | 0 |

## Threshold sweep

| Flag at points >= | Precision | Recall | False alarms |
|---|---|---|---|
| 5 | 75% | 100% | 5 of 22 |
| 10 | 75% | 100% | 5 of 22 |
| 15 | 78% | 93% | 4 of 22 |
| 20 | 81% | 87% | 3 of 22 |
| 25 | 87% | 87% | 2 of 22 |
| 30 | 86% | 80% | 2 of 22 |
| 35 | 91% | 67% | 1 of 22 |
| 40 | 100% | 67% | 0 of 22 |
| 50 | 100% | 47% | 0 of 22 |
| 65 | 100% | 33% | 0 of 22 |

## Every listing

| ID | Label | Result | Points | Signals |
|---|---|---|---|---|
| scam-01 | scam | high | 75 | RENT_FAR_BELOW_MARKET, OWNER_UNAVAILABLE, PEER_TO_PEER_PAYMENT |
| scam-02 | scam | medium | 30 | PAYMENT_BEFORE_VIEWING |
| scam-03 | scam | high | 60 | PAYMENT_BEFORE_VIEWING, UNTRACEABLE_PAYMENT |
| scam-04 | scam | insufficient_data ❌ | 15 | OFF_PLATFORM_CONTACT |
| scam-05 | scam | high | 100 | RENT_FAR_BELOW_MARKET, OWNER_UNAVAILABLE, CANNOT_SHOW_UNIT, KEYS_MAILED, UNTRACEABLE_PAYMENT |
| scam-06 | scam | high | 65 | OWNER_UNAVAILABLE, CANNOT_SHOW_UNIT, KEYS_MAILED |
| scam-07 | scam | medium | 45 | PAYMENT_BEFORE_VIEWING, PERSONAL_INFO_REQUEST |
| scam-08 | scam | high | 60 | PAYMENT_BEFORE_VIEWING, UNTRACEABLE_PAYMENT |
| scam-09 | scam | high | 65 | CANNOT_SHOW_UNIT, PAYMENT_BEFORE_VIEWING, PEER_TO_PEER_PAYMENT |
| scam-10 | scam | medium | 40 | PAYMENT_BEFORE_VIEWING, PEER_TO_PEER_PAYMENT |
| scam-11 | scam | high | 65 | OWNER_UNAVAILABLE, PAYMENT_BEFORE_VIEWING, PEER_TO_PEER_PAYMENT |
| scam-12 | scam | insufficient_data ❌ | 10 | PEER_TO_PEER_PAYMENT |
| scam-13 | scam | medium | 30 | PAYMENT_BEFORE_VIEWING |
| scam-14 | scam | medium | 25 | OFF_PLATFORM_CONTACT, PEER_TO_PEER_PAYMENT |
| scam-15 | scam | medium | 40 | PAYMENT_BEFORE_VIEWING, PEER_TO_PEER_PAYMENT |
| legit-01 | legit | low | 0 | none |
| legit-02 | legit | insufficient_data | 0 | none |
| legit-03 | legit | insufficient_data | 10 | PEER_TO_PEER_PAYMENT |
| legit-04 | legit | insufficient_data | 0 | none |
| legit-05 | legit | insufficient_data | 0 | none |
| legit-06 | legit | insufficient_data | 0 | none |
| legit-07 | legit | insufficient_data | 0 | none |
| legit-08 | legit | insufficient_data | 0 | none |
| legit-09 | legit | insufficient_data | 0 | none |
| legit-10 | legit | insufficient_data | 0 | none |
| legit-11 | legit | insufficient_data | 0 | none |
| legit-12 | legit | medium ❌ | 30 | PAYMENT_BEFORE_VIEWING |
| legit-13 | legit | medium ❌ | 35 | RENT_FAR_BELOW_MARKET |
| legit-14 | legit | medium ❌ | 20 | RENT_BELOW_MARKET |
| legit-15 | legit | insufficient_data | 0 | none |
| legit-16 | legit | insufficient_data | 0 | none |
| legit-17 | legit | insufficient_data | 0 | none |
| legit-18 | legit | insufficient_data | 0 | none |
| legit-19 | legit | low | 0 | none |
| legit-20 | legit | insufficient_data | 0 | none |
| legit-21 | legit | low | 15 | OFF_PLATFORM_CONTACT |
| legit-22 | legit | insufficient_data | 0 | none |
