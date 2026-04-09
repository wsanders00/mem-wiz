from __future__ import annotations


FACTOR_VALUES = {0.0, 0.25, 0.5, 0.75, 1.0}
FACTOR_WEIGHTS = {
    "reuse": 0.25,
    "durability": 0.20,
    "evidence": 0.20,
    "specificity": 0.15,
    "novelty": 0.10,
    "scope_fit": 0.10,
}
RETAIN_THRESHOLD = 0.55
PROMOTE_THRESHOLD = 0.78
GLOBAL_PROMOTION_MIN_DURABILITY = 0.70
GLOBAL_PROMOTION_MIN_EVIDENCE = 0.80
DIGEST_BUDGETS = {
    "global": {"bullets": 20, "bytes": 3000},
    "workspace": {"bullets": 40, "bytes": 6000},
}
DISQUALIFIERS = {
    "secret_like": "secret-like content",
    "filler": "transient conversational filler",
    "status": "one-off task status updates",
    "vague": "vague, non-actionable summaries",
    "unsupported_guess": "unsupported guesses with no acceptable evidence",
    "strong_duplicate": "strong duplicates in the target scope",
}
