from __future__ import annotations

import os

APP_ENV = os.getenv("REVIVE_ENV", "development")
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")
RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")
RAZORPAY_BASE_URL = os.getenv("RAZORPAY_BASE_URL", "https://api.razorpay.com/v1")
MOCK_EXTERNAL_ACTIONS = os.getenv("MOCK_EXTERNAL_ACTIONS", "true").lower() not in {"0", "false", "no"}
CORS_ORIGINS = [x.strip() for x in os.getenv("CORS_ORIGINS", "*").split(",") if x.strip()]
