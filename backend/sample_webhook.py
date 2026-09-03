from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import urllib.request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://localhost:8000/api/webhooks/razorpay')
    parser.add_argument('--secret', required=True)
    parser.add_argument('--event', choices=['payment.failed','payment.captured','payment_link.paid','payment_link.expired','payment_link.cancelled'], default='payment.failed')
    parser.add_argument('--payment-id', default='pay_demo_001')
    parser.add_argument('--link-id', default='plink_demo_evt_demo')
    parser.add_argument('--reference-id', default='evt_demo')
    args = parser.parse_args()
    if args.event.startswith('payment_link.'):
        body = {
            'id': f'wh_{args.event.replace(".", "_")}_{args.reference_id}',
            'event': args.event,
            'payload': {'payment_link': {'entity': {
                'id': args.link_id,
                'amount': 1850000,
                'amount_paid': 1850000 if args.event == 'payment_link.paid' else 0,
                'currency': 'INR',
                'reference_id': args.reference_id,
                'short_url': f'http://localhost:5500/pay/{args.reference_id}',
                'status': 'paid' if args.event == 'payment_link.paid' else ('expired' if args.event == 'payment_link.expired' else 'cancelled')
            }}}
        }
    else:
        body = {
            'id': f'wh_{args.event.replace(".", "_")}_{args.payment_id}',
            'event': args.event,
            'payload': {'payment': {'entity': {
                'id': args.payment_id,
                'amount': 1850000,
                'currency': 'INR',
                'email': 'demo@example.com',
                'error_reason': 'insufficient_funds' if args.event == 'payment.failed' else None,
                'status': 'captured' if args.event == 'payment.captured' else 'failed'
            }}}
        }
    raw = json.dumps(body, separators=(',', ':')).encode()
    sig = hmac.new(args.secret.encode(), raw, hashlib.sha256).hexdigest()
    req = urllib.request.Request(args.url, data=raw, method='POST', headers={'Content-Type':'application/json','X-Razorpay-Signature':sig})
    with urllib.request.urlopen(req, timeout=10) as r:
        print(r.read().decode())

if __name__ == '__main__':
    main()
