"""Deterministic solvers: answers that need no model at all. Each returns None when it does not apply, so the
orchestrator can fall through to the next-cheapest strategy. Results include the method, so they are auditable."""
from __future__ import annotations

import re
from datetime import UTC, date, datetime
from typing import Any

from .tools import _calc

NUM = r"(-?\d+(?:[.,]\d+)?)"


def _f(s: str) -> float:
    return float(s.replace(",", "."))


def _fmt(v: float) -> str:
    return str(int(v)) if v == int(v) else f"{v:.4f}".rstrip("0").rstrip(".")


def arithmetic(q: str) -> dict[str, Any] | None:
    m = re.fullmatch(r"\s*(?:what is|what's|calculate|compute|räkna ut|vad är)?\s*([-+*/().%\d\s,^]+?)\s*[?=]?\s*", q, re.I)
    if not m or not re.search(r"\d\s*[-+*/^%]\s*\(?\s*\d", m.group(1)):
        return None
    expr = m.group(1).replace("^", "**").replace(",", ".")
    expr = re.sub(r"(\d+(?:\.\d+)?)\s*%", r"(\1/100)", expr)
    try:
        v = _calc(expr)
    except (ValueError, SyntaxError, ZeroDivisionError):
        return None
    return {"answer": _fmt(v), "value": v, "method": f"safe arithmetic: {expr.strip()}"}


def percent_of(q: str) -> dict[str, Any] | None:
    m = re.search(NUM + r"\s*%\s*(?:of|av)\s*" + NUM, q, re.I)
    if not m:
        return None
    v = _f(m.group(1)) / 100 * _f(m.group(2))
    return {"answer": _fmt(v), "value": v, "method": f"{m.group(1)}% × {m.group(2)}"}


def vat(q: str) -> dict[str, Any] | None:
    """'240 including 25% VAT, price excluding VAT?' / '100 excluding 25% VAT, price including?'"""
    m = re.search(NUM + r"\s*(?:sek|kr|eur|€|usd|\$)?\s*(incl(?:uding|\.)?|inkl(?:usive|\.)?|excl(?:uding|\.)?|exkl(?:usive|\.)?)\s*" + NUM + r"\s*%\s*(?:vat|moms)", q, re.I)
    if not m:
        return None
    amount, kind, rate = _f(m.group(1)), m.group(2).lower(), _f(m.group(3)) / 100
    if kind.startswith(("incl", "inkl")):
        v = amount / (1 + rate)
        return {"answer": _fmt(round(v, 2)), "value": v, "method": f"{amount} ÷ (1 + {rate:g}) — price excluding VAT"}
    v = amount * (1 + rate)
    return {"answer": _fmt(round(v, 2)), "value": v, "method": f"{amount} × (1 + {rate:g}) — price including VAT"}


def days_between(q: str) -> dict[str, Any] | None:
    ds = re.findall(r"(\d{4}-\d{2}-\d{2})", q)
    if len(ds) != 2 or not re.search(r"days?|dagar", q, re.I):
        return None
    try:
        a, b = (date.fromisoformat(d) for d in ds)
    except ValueError:
        return None
    return {"answer": str(abs((b - a).days)), "value": abs((b - a).days), "method": f"calendar difference {ds[0]} → {ds[1]}"}


def now(q: str) -> dict[str, Any] | None:
    if not re.search(r"\b(what(?:'s| is) (?:the )?(?:date|time|day)(?: today| now)?|today's date|vilket datum|vad är klockan)\b", q, re.I):
        return None
    t = datetime.now(UTC)
    return {"answer": t.strftime("%A %Y-%m-%d %H:%M UTC"), "value": t.isoformat(), "method": "system clock (UTC)"}


UNITS = {("km", "mi"): 0.621371, ("mi", "km"): 1.609344, ("kg", "lb"): 2.204623, ("lb", "kg"): 0.453592, ("m", "ft"): 3.280840,
         ("ft", "m"): 0.3048, ("l", "gal"): 0.264172, ("gal", "l"): 3.785412, ("cm", "in"): 0.393701, ("in", "cm"): 2.54}
ALIASES = {"miles": "mi", "mile": "mi", "kilometers": "km", "kilometres": "km", "kilograms": "kg", "pounds": "lb", "lbs": "lb",
           "meters": "m", "metres": "m", "feet": "ft", "foot": "ft", "liters": "l", "litres": "l", "gallons": "gal", "inches": "in",
           "inch": "in", "centimeters": "cm", "centimetres": "cm", "c": "c", "f": "f", "celsius": "c", "fahrenheit": "f"}


def convert(q: str) -> dict[str, Any] | None:
    m = re.search(NUM + r"\s*°?\s*([a-z]+)\s+(?:to|in|into|i)\s+°?([a-z]+)", q, re.I)
    if not m:
        return None
    v, a, b = _f(m.group(1)), ALIASES.get(m.group(2).lower(), m.group(2).lower()), ALIASES.get(m.group(3).lower(), m.group(3).lower())
    if (a, b) == ("c", "f"):
        r = v * 9 / 5 + 32
    elif (a, b) == ("f", "c"):
        r = (v - 32) * 5 / 9
    elif (a, b) in UNITS:
        r = v * UNITS[(a, b)]
    else:
        return None
    return {"answer": f"{_fmt(round(r, 4))} {b}", "value": r, "method": f"unit conversion {a}→{b}"}


SOLVERS = (now, days_between, vat, percent_of, convert, arithmetic)


def solve(q: str) -> dict[str, Any] | None:
    for fn in SOLVERS:
        r = fn(q)
        if r is not None:
            return {**r, "solver": fn.__name__}
    return None
