# ReviveAI hosted email: Resend

The hosted application uses **Resend over HTTPS** for real email delivery. SMTP is retained only as a backend compatibility path for local/self-hosted deployments and is not exposed in the React UI.

## Render
No global Resend secret is required. Each merchant configures their own Resend API key in **Merchant Settings → Recovery email sender**.

## Merchant setup
1. Choose `Demo — no real email` for safe UI testing, or `Resend API — real email` for real delivery.
2. Enter the recovery sender email.
3. For Resend mode, enter the merchant's Resend API key.
4. Save settings.
5. Use **Send test email** to verify delivery.

The API key is stored server-side and is never returned from `/api/auth/me`.

## Sender verification
The sender address must be allowed by the merchant's Resend account/domain configuration. Do not use an arbitrary Gmail address unless it is permitted by the Resend account.

## Local fallback
The Python email adapter still contains an SMTP branch for developers who run the service outside hosted environments. The production React application does not present SMTP configuration fields.
