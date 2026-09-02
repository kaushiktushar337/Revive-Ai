from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib
import numpy as np

MODEL_PATH = Path(__file__).with_name("recovery_model.joblib")
FEATURES = [
    "amount",
    "previous_success_rate",
    "days_since_last_success",
    "prior_contacts",
    "customer_value",
    "event_age_hours",
    "is_subscription",
]


def train_model() -> None:
    rng = np.random.default_rng(42)
    n = 6000
    X = np.column_stack(
        [
            rng.lognormal(mean=8.5, sigma=0.9, size=n),
            rng.beta(7, 2, size=n),
            rng.integers(0, 90, size=n),
            rng.integers(0, 5, size=n),
            rng.lognormal(mean=9.0, sigma=1.0, size=n),
            rng.integers(1, 168, size=n),
            rng.integers(0, 2, size=n),
        ]
    )
    amount = X[:, 0]
    success = X[:, 1]
    delay = X[:, 2]
    contacts = X[:, 3]
    value = X[:, 4]
    age = X[:, 5]
    subscription = X[:, 6]

    logits = (
        -1.2
        + 2.8 * success
        + 0.45 * subscription
        + 0.25 * np.log1p(value / 10000)
        - 0.012 * delay
        - 0.30 * contacts
        - 0.0015 * age
        - 0.000002 * amount
    )
    probability = 1 / (1 + np.exp(-logits))
    y = (rng.random(n) < probability).astype(int)

    from sklearn.ensemble import RandomForestClassifier

    clf = RandomForestClassifier(
        n_estimators=180,
        max_depth=10,
        random_state=42,
        class_weight="balanced",
        n_jobs=-1,
    )
    clf.fit(X, y)
    joblib.dump(clf, MODEL_PATH)


def get_model():
    if not MODEL_PATH.exists():
        train_model()
    return joblib.load(MODEL_PATH)


def predict_probability(event: dict[str, Any]) -> float:
    model = get_model()
    row = [[
        float(event.get("amount") or 0),
        float(event.get("previous_success_rate") or 0),
        float(event.get("days_since_last_success") or 0),
        float(event.get("prior_contacts") or 0),
        float(event.get("customer_value") or event.get("amount") or 0),
        float(event.get("event_age_hours") or 1),
        1.0 if event.get("is_subscription") else 0.0,
    ]]
    return float(model.predict_proba(row)[0][1])
