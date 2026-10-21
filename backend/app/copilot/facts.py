"""Helpers over the customer-visible order facts (see cs.order_facts)."""


def pick_claim(claims: list[dict], text: str) -> dict | None:
    """The claim a customer message is most likely about: the one whose item they name, else the newest."""
    for c in claims:
        for ln in c.get("lines", []):
            if len(ln["title"]) >= 4 and ln["title"][:4] in text:
                return c
    return claims[0] if claims else None
