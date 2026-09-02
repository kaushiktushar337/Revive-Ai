from engine import bounded_decision


def base(**overrides):
    data = {
        "event_type": "payment_failed",
        "customer": "Test",
        "amount": 18500,
        "failure_reason": "insufficient_funds",
        "previous_success_rate": 0.86,
        "days_since_last_success": 5,
        "prior_contacts": 0,
        "customer_value": 74000,
        "event_age_hours": 1,
        "is_subscription": True,
    }
    data.update(overrides)
    return data


def test_high_probability_payment_retries():
    decision = bounded_decision(base(), 0.84)
    assert decision.recommended_action == "retry_payment"
    assert decision.delay_hours == 24


def test_expired_card_updates_payment_method():
    decision = bounded_decision(base(failure_reason="expired_card"), 0.9)
    assert decision.recommended_action == "send_payment_update"


def test_high_value_requires_human_approval():
    decision = bounded_decision(base(amount=150000), 0.9)
    assert decision.recommended_action == "escalate"


def test_repeated_messages_stop():
    decision = bounded_decision(base(prior_contacts=3), 0.8)
    assert decision.recommended_action == "escalate"
