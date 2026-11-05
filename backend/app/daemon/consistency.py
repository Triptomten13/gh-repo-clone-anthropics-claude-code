"""Self-consistency for deep reasoning: sample the reasoning model several times and keep the majority final answer.
A single sample of a small reasoning model can be confidently wrong; agreement across independent samples raises
confidence (it does not prove correctness) and disagreement is reported, never hidden."""
from __future__ import annotations

import re
from collections import Counter
from typing import Any

ANSWER_LINE = re.compile(r"(?im)^\W*answer\W*:\s*(.+)$")
NUMBER = re.compile(r"-?\d+(?:[.,]\d+)?")


def final_answer(text: str) -> str:
    """Canonical final answer: the last 'Answer: …' line (else the last non-empty line), normalised; numbers compare by value."""
    t = text or ""
    m = ANSWER_LINE.findall(t)
    raw = m[-1] if m else next((ln for ln in reversed(t.strip().splitlines()) if ln.strip()), "")
    raw = re.sub(r"[*_`$]", "", raw).strip().rstrip(".").strip()
    nums = NUMBER.findall(raw.replace(" ", ""))
    if nums:
        v = float(nums[-1].replace(",", "."))
        return f"num:{v:g}"
    return "txt:" + re.sub(r"\s+", " ", raw.lower())


def vote(texts: list[str]) -> dict[str, Any]:
    finals = [final_answer(t) for t in texts]
    winner, n = Counter(finals).most_common(1)[0]
    return {"winner": winner, "index": finals.index(winner), "finals": finals, "agreement": f"{n}/{len(finals)}",
            "majority": n * 2 > len(finals)}


def settled(texts: list[str], planned: int) -> bool:
    """Stop early once the leading answer already holds a majority of the planned samples."""
    if not texts:
        return False
    n = Counter(final_answer(t) for t in texts).most_common(1)[0][1]
    return n * 2 > planned
