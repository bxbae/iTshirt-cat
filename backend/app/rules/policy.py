"""Store policy as numbers. The Markdown KB (app/kb) explains the same rules to customers and agents;
tests keep the two in step."""

FREE_SHIPPING_MIN = 15_000      # items total (after discount) for free shipping
SHIPPING_FEE = 2_500
RETURN_FEE = 3_000              # return shipping paid by the customer on a change-of-mind return
MIND_WINDOW_DAYS = 7            # change of mind: days after delivery
DEFECT_WINDOW_DAYS = 30         # defect / damage / wrong item: days after delivery
LATE_GRACE_DAYS = 3             # compensation starts when delivery is this many days past the estimate
LATE_TIERS = [(7, 3_000), (3, 1_000)]   # (days late >=, points)
DEFECT_COMPENSATION = 2_000     # points, paid after the returned item passes inspection
AUTO_LIMIT = 100_000            # refund + compensation above this needs an agent
ABUSE_REVIEW_SCORE = 60         # at or above: never auto-approved
ABUSE_WINDOW_DAYS = 90

SELLER_FAULT = {"defect", "wrong_item", "damaged"}
REASONS = ["change_of_mind", "defect", "wrong_item", "damaged", "late_delivery", "missing_item", "other"]
TYPES = ["cancel", "return", "exchange", "compensation"]

# Which KB section explains each rule, so a decision can cite its source.
RULE_REFS = {
    "INVALID_REASON": "KB-DEL-01#2",
    "OWNER_MISMATCH": "KB-PAY-01#3",
    "ITEM_NOT_IN_ORDER": "KB-PAY-01#3",
    "ALREADY_CLAIMED": "KB-REF-01#5",
    "QTY_ADJUSTED": "KB-PAY-01#3",
    "CANCEL_TOO_LATE": "KB-CAN-01#2",
    "ALREADY_CANCELLED": "KB-CAN-01#1",
    "NOT_DELIVERED_YET": "KB-REF-01#1",
    "CANCEL_INSTEAD": "KB-CAN-01#1",
    "WINDOW_MIND_EXPIRED": "KB-REF-01#1",
    "WINDOW_DEFECT_EXPIRED": "KB-REF-01#2",
    "NON_RETURNABLE": "KB-REF-01#3",
    "UNSEALED": "KB-REF-01#3",
    "EBOOK_DEFECT": "KB-REF-01#3",
    "NEED_EVIDENCE": "KB-REF-01#2",
    "NOT_LATE": "KB-DEL-01#2",
    "LATE_COMPENSATION": "KB-DEL-01#2",
    "ALREADY_COMPENSATED": "KB-DEL-01#2",
    "MISSING_ITEM_INVESTIGATE": "KB-DEL-01#4",
    "RETURN_FEE": "KB-REF-01#4",
    "SHIPPING_FEE_LOST": "KB-REF-01#4",
    "AMOUNT_ADJUSTED": "KB-PAY-01#3",
    "AMOUNT_EXCEEDS_RECEIPT": "KB-PAY-01#3",
    "DEFECT_COMPENSATION": "KB-CMP-01#1",
    "OVER_AUTO_LIMIT": "KB-CMP-01#3",
    "ABUSE_SUSPECTED": "KB-CMP-01#3",
    "OTHER_REASON": "KB-CMP-01#3",
    "EXCHANGE_STOCK_LOW": "KB-CMP-01#2",
}
