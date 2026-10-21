"""Mask personal data before it reaches the LLM, logs or a reply."""
import re

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# 13-19 digits, optionally grouped by spaces or dashes; confirmed with the Luhn check below.
CARD = re.compile(r"(?<![0-9A-Za-z_.])(?:\d[ -]?){12,18}\d(?![0-9A-Za-z_])")
# Korean mobile/landline numbers, with or without separators (010-1234-5678, 01012345678, 02-123-4567).
# Boundaries are ASCII-only on purpose: \w would treat a Korean particle ("010-1234-5678로") as part of the number.
PHONE = re.compile(r"(?<![0-9A-Za-z_.-])(?:\+82[ -]?)?0\d{1,2}[ -]?\d{3,4}[ -]?\d{4}(?![0-9A-Za-z_-])")

SUPPORT_DOMAINS = ("catbooks.example",)


def _luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def find_pii(text: str) -> list[dict]:
    found: list[dict] = []
    for m in EMAIL.finditer(text):
        if not m.group().lower().endswith(SUPPORT_DOMAINS):
            found.append({"type": "email", "span": m.span()})
    for m in CARD.finditer(text):
        digits = re.sub(r"\D", "", m.group())
        if 13 <= len(digits) <= 19 and _luhn_ok(digits):
            found.append({"type": "card", "span": m.span()})
    for m in PHONE.finditer(text):
        if not any(f["span"][0] <= m.start() < f["span"][1] for f in found):
            found.append({"type": "phone", "span": m.span()})
    return sorted(found, key=lambda f: f["span"][0])


def mask_pii(text: str) -> tuple[str, list[str]]:
    """Return the text with personal data replaced by [EMAIL]/[CARD]/[PHONE] and the types found."""
    found = find_pii(text)
    out, last = [], 0
    for f in found:
        start, end = f["span"]
        if start < last:
            continue
        out.append(text[last:start])
        out.append(f"[{f['type'].upper()}]")
        last = end
    out.append(text[last:])
    return "".join(out), [f["type"] for f in found]
