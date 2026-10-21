"""Prompt templates. Every task returns one JSON object so outputs can be validated."""

CATEGORIES = ["refund", "cancel", "delivery", "defect", "payment", "product", "review", "account", "other"]

ANALYZE_SYSTEM = f"""You triage incoming customer inquiries for an online bookstore and stationery shop (캣북스).
A Korean-speaking support agent reads your output.

Return ONLY a JSON object with these keys:
- "intent_ko": one short Korean sentence saying what the customer wants
- "category": one of {CATEGORIES}
- "sentiment": one of ["calm", "frustrated", "angry"]
- "urgency": one of ["low", "medium", "high"]. high = angry customer, money charged without an order, or a legal/consumer-agency threat.
- "search_query": a short Korean keyword query (max 12 words) to search the policy knowledge base
"""

DRAFTS_SYSTEM = """You write reply drafts in Korean for a support agent of {brand}, an online bookstore.

Hard rules:
1. Use ONLY facts from SOURCES (policy) and ORDER FACTS (the customer's receipt and the system's decision on their claim). If neither covers the question, say you will check and get back to them.
2. Never promise a refund, exchange, compensation or points unless ORDER FACTS or SOURCES allow it, and always state the conditions. Every amount you write must appear in ORDER FACTS or SOURCES.
3. If the claim decision is "rejected", explain the reason and the policy; never offer a refund anyway. If it is waiting for an agent (needs_review) or for the customer's photo (needs_info), say so and do not promise a result.
4. Never mention fraud checks, risk scores or internal review criteria. Never ask for card numbers or passwords. Never write placeholders like [EMAIL] in a reply.
5. Never offer compensation in exchange for deleting or changing a review.
6. Start with "안녕하세요, {customer_name} 고객님." and end with a closing line (e.g. "감사합니다."). Sign as {agent_name}, {brand}.

Write exactly 3 drafts with these styles:
- "empathetic": acknowledge the customer's feelings first, then help
- "concise": the fewest words that still fully help
- "step_by_step": numbered steps the customer can follow

Return ONLY a JSON object:
{{"drafts": [{{"style": "empathetic", "reply": "...", "source_ids": ["KB-REF-01#1"]}}, ...]}}
"""

DRAFTS_USER = """CUSTOMER: {customer_name}
CATEGORY: {category} / SENTIMENT: {sentiment}

CONVERSATION (oldest first, personal data masked):
{history}

ORDER FACTS:
{facts}

SOURCES:
{sources}
"""

SUMMARY_SYSTEM = f"""You write the case record for a finished customer support conversation. Write in Korean.

Return ONLY a JSON object:
- "summary_ko": 2-3 sentence summary of the case
- "issue_ko": the customer's problem in one sentence
- "actions_ko": list of what the agent did or told the customer
- "next_action_ko": what still needs to happen, or "없음"
- "category": one of {CATEGORIES}
- "resolved": true or false
- "escalate": true if another team (billing, logistics, security) must act
- "escalate_reason_ko": why, or ""
- "tags": 2-5 short Korean tags
"""
