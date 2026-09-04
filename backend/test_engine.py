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


def test_invoice_reasons_are_specific_to_context():
    a = bounded_decision(base(event_type="invoice_overdue", amount=5000, days_overdue=5, previous_success_rate=0.92, prior_contacts=0), 0.62)
    b = bounded_decision(base(event_type="invoice_overdue", amount=5000, days_overdue=18, previous_success_rate=0.55, prior_contacts=2), 0.28)
    assert a.action_reason != b.action_reason
    assert "5 days overdue" in a.action_reason
    assert "18 days" in b.action_reason


def test_checkout_reason_mentions_freshness():
    decision = bounded_decision(base(event_type="checkout_abandoned", amount=42000, event_age_hours=3, previous_success_rate=0.92), 0.8)
    assert decision.recommended_action == "send_recovery_message"
    assert "3 hours ago" in decision.action_reason


def test_risk_reason_contains_model_and_context():
    decision = bounded_decision(base(event_type="invoice_overdue", days_overdue=8, prior_contacts=1), 0.55)
    assert "8 days overdue" in decision.risk_reason
    assert "model recovery probability 55%" in decision.risk_reason


def test_payment_link_recommendation_includes_email_followup():
    decision = bounded_decision(base(event_type="invoice_overdue", days_overdue=7, previous_success_rate=0.80, prior_contacts=0), 0.70)
    assert decision.recommended_action == "send_payment_link"
    assert "personalized recovery email" in decision.action_reason


def test_recovery_message_is_link_eligible_policy():
    decision = bounded_decision(base(event_type="invoice_overdue", days_overdue=18, previous_success_rate=0.55, prior_contacts=2), 0.50)
    assert decision.recommended_action == "send_recovery_message"


def test_recovery_message_email_uses_created_payment_link():
    import sqlite3
    import main as main_module
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.execute('CREATE TABLE events (recommended_action TEXT, recovery_link_url TEXT, currency TEXT, amount REAL, customer TEXT)')
    conn.execute('INSERT INTO events VALUES (?,?,?,?,?)', ('send_recovery_message', 'https://uat.payu.example/link-123', 'INR', 2500, 'Demo Customer'))
    row = conn.execute('SELECT * FROM events').fetchone()
    subject, body = main_module._email_content(row)
    assert '2,500' in subject
    assert 'https://uat.payu.example/link-123' in body
    conn.close()
