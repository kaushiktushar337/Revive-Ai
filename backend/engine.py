from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Decision:
    risk_score: int
    recovery_probability: float
    risk_reason: str
    recommended_action: str
    action_reason: str
    delay_hours: int


def bounded_decision(event: dict[str, Any], probability: float) -> Decision:
    amount = float(event.get("amount", 0))
    event_type = event.get("event_type", "unknown")
    failure_reason = (event.get("failure_reason") or "").lower()
    days_overdue = int(event.get("days_overdue") or 0)
    previous_success_rate = float(event.get("previous_success_rate") or 0.0)
    prior_contacts = int(event.get("prior_contacts") or 0)
    customer_value = float(event.get("customer_value") or amount)

    probability = max(0.0, min(1.0, probability))
    risk_score = round((1 - probability) * 40 + min(amount / 10000, 1) * 30 + min(prior_contacts / 5, 1) * 15 + min(days_overdue / 30, 1) * 15)
    risk_score = max(0, min(100, risk_score))

    if event_type == "payment_failed":
        if failure_reason in {"expired_card", "card_expired"}:
            action = "send_payment_update"
            reason = "The failure suggests the payment method needs updating rather than another blind retry."
            delay = 0
        elif failure_reason in {"insufficient_funds", "bank_declined", "temporary_decline", "network_error"} and probability >= 0.60:
            action = "retry_payment"
            reason = "The customer has a reasonable recovery probability, so a bounded retry is the lowest-friction intervention."
            delay = 24 if failure_reason == "insufficient_funds" else 2
        elif probability >= 0.45:
            action = "send_recovery_message"
            reason = "A message can prompt recovery without repeatedly charging the customer."
            delay = 0
        else:
            action = "escalate"
            reason = "Recovery probability is low enough that automated retries risk unnecessary friction."
            delay = 0

    elif event_type == "checkout_abandoned":
        if probability >= 0.65 and prior_contacts < 2:
            action = "send_recovery_message"
            reason = "High-value, recently abandoned checkouts are strong candidates for one recovery message."
            delay = 1
        elif probability >= 0.40 and prior_contacts == 0:
            action = "send_recovery_message"
            reason = "A single low-friction reminder is justified because there has been no prior contact."
            delay = 4
        else:
            action = "do_nothing"
            reason = "The expected recovery benefit does not justify another customer intervention."
            delay = 0

    elif event_type == "invoice_overdue":
        if days_overdue <= 3 and previous_success_rate >= 0.75:
            action = "do_nothing"
            reason = "The customer usually pays and is only slightly overdue, so intervention could create unnecessary friction."
            delay = 24
        elif days_overdue <= 14 and probability >= 0.45:
            action = "send_payment_link"
            reason = "A direct payment option is appropriate before escalation."
            delay = 0
        elif probability >= 0.35 and prior_contacts < 3:
            action = "send_recovery_message"
            reason = "A structured reminder is preferred before human escalation."
            delay = 0
        else:
            action = "escalate"
            reason = "The invoice is sufficiently overdue or repeatedly contacted to justify human follow-up."
            delay = 0
    else:
        action = "do_nothing"
        reason = "No supported recovery workflow exists for this event type."
        delay = 0

    if amount >= 100000 and action in {"retry_payment", "send_payment_update"}:
        action = "escalate"
        reason = "High-value payment actions are bounded by a human-approval threshold in the MVP."
        delay = 0

    if prior_contacts >= 3 and action in {"send_recovery_message", "retry_payment", "send_payment_update", "send_payment_link"}:
        action = "escalate"
        reason = "The customer has already received multiple contacts, so the bounded policy stops further automated intervention."
        delay = 0

    risk_reason = f"{event_type.replace('_', ' ').title()} for ₹{amount:,.0f}; recovery probability {probability:.0%}."
    return Decision(
        risk_score=risk_score,
        recovery_probability=probability,
        risk_reason=risk_reason,
        recommended_action=action,
        action_reason=reason,
        delay_hours=delay,
    )
