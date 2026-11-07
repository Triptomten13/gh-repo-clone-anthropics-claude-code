"""User-controlled memory. Items are inspectable, editable, exportable and deletable by their owner.
Credentials and national ID / card numbers are refused; other personal data is flagged."""
from __future__ import annotations

import re

REFUSE = [
    (r"\b(19|20)?\d{6}[-+]?\d{4}\b", "Swedish personal identity number (personnummer)"),
    (r"(sk-ant-|sk-[a-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16})", "API key or access token"),
    (r"\b(password|lösenord|passwd)\s*[:=]", "password"),
]
WARN = [(r"[\w.+-]+@[\w-]+\.[\w.]+", "email address"), (r"\+?\d[\d \-]{8,}\d", "phone number")]


def _luhn(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
        alt = not alt
    return total % 10 == 0


def screen(text: str) -> dict[str, list[str]]:
    refuse = [why for pat, why in REFUSE if re.search(pat, text, re.I)]
    for m in re.finditer(r"\b(?:\d[ -]?){13,19}\b", text):
        if _luhn(re.sub(r"\D", "", m.group(0))):
            refuse.append("payment card number")
    warn = [why for pat, why in WARN if re.search(pat, text)]
    return {"refuse": sorted(set(refuse)), "warn": sorted(set(warn))}
