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


def _pct(value: float) -> str:
    return f"{max(0, min(1, value)):.0%}"


def _money(value: float) -> str:
    return f"₹{value:,.0f}"


def _payment_failure_reason(failure_reason: str) -> str:
    mapping = {
        "expired_card": "expired card details",
        "card_expired": "expired card details",
        "insufficient_funds": "insufficient funds",
        "bank_declined": "a bank decline",
        "temporary_decline": "a temporary decline",
        "network_error": "a temporary network error",
    }
    return mapping.get(failure_reason, failure_reason.replace("_", " ") or "an unknown payment issue")


def _risk_reason(event_type: str, amount: float, probability: float, previous_success_rate: float,
                 days_overdue: int, prior_contacts: int, days_since_last_success: int,
                 event_age_hours: float, failure_reason: str) -> str:
    if event_type == "invoice_overdue":
        parts = [f"{days_overdue} days overdue", f"{_pct(previous_success_rate)} historical payment success"]
        if prior_contacts:
            parts.append(f"{prior_contacts} prior contact{'s' if prior_contacts != 1 else ''}")
        if days_since_last_success:
            parts.append(f"{days_since_last_success} days since the last successful payment")
        return f"{_money(amount)} at risk • " + " • ".join(parts) + f" • model recovery probability {_pct(probability)}."
    if event_type == "payment_failed":
        parts = [f"payment failed due to {_payment_failure_reason(failure_reason)}", f"{_pct(previous_success_rate)} historical payment success"]
        if prior_contacts:
            parts.append(f"{prior_contacts} prior contact{'s' if prior_contacts != 1 else ''}")
        parts.append(f"event age {event_age_hours:g}h")
        return f"{_money(amount)} at risk • " + " • ".join(parts) + f" • model recovery probability {_pct(probability)}."
    if event_type == "checkout_abandoned":
        parts = [f"checkout abandoned {event_age_hours:g}h ago", f"{_pct(previous_success_rate)} historical payment success"]
        if prior_contacts:
            parts.append(f"{prior_contacts} prior contact{'s' if prior_contacts != 1 else ''}")
        return f"{_money(amount)} at risk • " + " • ".join(parts) + f" • model recovery probability {_pct(probability)}."
    return f"{_money(amount)} at risk • model recovery probability {_pct(probability)}."


def bounded_decision(event: dict[str, Any], probability: float) -> Decision:
    """Convert the model probability into an explainable, bounded recovery action.

    The ML model estimates recovery probability. This policy layer chooses the action so
    recommendations remain deterministic, safe, and explainable to a business operator.
    """
    amount = float(event.get("amount", 0))
    event_type = event.get("event_type", "unknown")
    failure_reason = (event.get("failure_reason") or "").lower()
    days_overdue = int(event.get("days_overdue") or 0)
    previous_success_rate = float(event.get("previous_success_rate") or 0.0)
    prior_contacts = int(event.get("prior_contacts") or 0)
    customer_value = float(event.get("customer_value") or amount)
    days_since_last_success = int(event.get("days_since_last_success") or 0)
    event_age_hours = float(event.get("event_age_hours") or 0)

    probability = max(0.0, min(1.0, probability))
    risk_score = round(
        (1 - probability) * 40
        + min(amount / 10000, 1) * 30
        + min(prior_contacts / 5, 1) * 15
        + min(days_overdue / 30, 1) * 15
    )
    risk_score = max(0, min(100, risk_score))

    if event_type == "payment_failed":
        if failure_reason in {"expired_card", "card_expired"}:
            action = "send_payment_update"
            reason = (
                f"The payment failed because the customer's card appears expired. "
                f"With {_pct(previous_success_rate)} historical payment success, an update request is more appropriate than another retry."
            )
            delay = 0
        elif failure_reason == "insufficient_funds" and probability >= 0.60:
            action = "retry_payment"
            reason = (
                f"The model estimates a {_pct(probability)} recovery chance and the failure points to insufficient funds. "
                f"A single retry after 24 hours gives the customer time to replenish funds without repeated charges."
            )
            delay = 24
        elif failure_reason in {"bank_declined", "temporary_decline", "network_error"} and probability >= 0.60:
            action = "retry_payment"
            reason = (
                f"The model estimates a {_pct(probability)} recovery chance and the failure looks temporary. "
                f"A bounded retry after a short wait is the lowest-friction intervention."
            )
            delay = 2
        elif probability >= 0.45:
            action = "send_recovery_message"
            reason = (
                f"Recovery probability is {_pct(probability)}, but the payment issue is not safe to retry automatically. "
                f"A single recovery message can prompt the customer to complete payment without another charge attempt."
            )
            delay = 0
        else:
            action = "escalate"
            reason = (
                f"The model estimates only a {_pct(probability)} recovery chance. "
                f"Automated retries are unlikely to help, so this case is better handled by a human."
            )
            delay = 0

    elif event_type == "checkout_abandoned":
        if probability >= 0.65 and prior_contacts < 2:
            action = "send_recovery_message"
            reason = (
                f"The checkout was abandoned {event_age_hours:g} hours ago and the model gives it a {_pct(probability)} recovery chance. "
                f"A single prompt is appropriate while purchase intent is still fresh."
            )
            delay = 1
        elif probability >= 0.40 and prior_contacts == 0:
            action = "send_recovery_message"
            reason = (
                f"The model estimates a {_pct(probability)} recovery chance and there have been no previous contacts. "
                f"A low-friction reminder is a reasonable first intervention."
            )
            delay = 4
        else:
            action = "do_nothing"
            reason = (
                f"The model estimates a {_pct(probability)} recovery chance and the customer has already been contacted "
                f"or shows weaker recovery signals. Waiting avoids unnecessary messaging."
            )
            delay = 0

    elif event_type == "invoice_overdue":
        if days_overdue <= 3 and previous_success_rate >= 0.75:
            action = "do_nothing"
            reason = (
                f"The invoice is only {days_overdue} day{'s' if days_overdue != 1 else ''} overdue and the customer historically pays on time "
                f"({_pct(previous_success_rate)} success). A short grace period is less intrusive than immediate outreach."
            )
            delay = 24
        elif days_overdue <= 14 and probability >= 0.45:
            action = "send_payment_link"
            reason = (
                f"The invoice is {days_overdue} days overdue and the model estimates a {_pct(probability)} recovery chance. "
                f"A direct payment link reduces friction and gives the customer a clear way to settle the balance. "
                f"Once the link is created, the recommended follow-up is a personalized recovery email containing that link."
            )
            delay = 0
        elif probability >= 0.35 and prior_contacts < 3:
            action = "send_recovery_message"
            reason = (
                f"The invoice is {days_overdue} days overdue with {_pct(previous_success_rate)} historical payment success "
                f"and {prior_contacts} prior contact{'s' if prior_contacts != 1 else ''}. "
                f"A targeted reminder is appropriate before escalating to a human."
            )
            delay = 0
        else:
            action = "escalate"
            reason = (
                f"The invoice has been outstanding for {days_overdue} days and the current recovery signals are weaker or repeatedly contacted. "
                f"Human follow-up is more appropriate than continuing automated reminders."
            )
            delay = 0
    else:
        action = "do_nothing"
        reason = "No supported recovery workflow exists for this event type, so no automated intervention is recommended."
        delay = 0

    if amount >= 100000 and action in {"retry_payment", "send_payment_update"}:
        action = "escalate"
        reason = (
            f"The balance is {_money(amount)}, above the automated payment-action threshold. "
            f"Human approval is required before attempting a high-value payment action."
        )
        delay = 0

    if prior_contacts >= 3 and action in {"send_recovery_message", "retry_payment", "send_payment_update", "send_payment_link"}:
        action = "escalate"
        reason = (
            f"The customer has already received {prior_contacts} recovery contacts. "
            f"The policy stops further automated outreach to avoid over-contacting and routes the case to a human."
        )
        delay = 0

    risk_reason = _risk_reason(
        event_type, amount, probability, previous_success_rate,
        days_overdue, prior_contacts, days_since_last_success,
        event_age_hours, failure_reason,
    )
    return Decision(
        risk_score=risk_score,
        recovery_probability=probability,
        risk_reason=risk_reason,
        recommended_action=action,
        action_reason=reason,
        delay_hours=delay,
    )
