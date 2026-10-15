import hashlib
import hmac

import razorpay
from django.conf import settings

from apps.properties.models import PropertyPaymentAccount


class PaymentAccountNotConfigured(Exception):
    pass


def get_credentials(property_obj):
    """
    Returns {'key_id', 'key_secret', 'webhook_secret'} for a property.
    Falls back to the global .env keys only if the property has no
    account of its own (keeps your existing test setup working).
    """
    if property_obj is not None:
        acct = PropertyPaymentAccount.objects.filter(
            property=property_obj, is_active=True
        ).first()
        if acct:
            return {
                'key_id': acct.razorpay_key_id,
                'key_secret': acct.razorpay_key_secret,
                'webhook_secret': acct.razorpay_webhook_secret,
            }

    if settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET:
        return {
            'key_id': settings.RAZORPAY_KEY_ID,
            'key_secret': settings.RAZORPAY_KEY_SECRET,
            'webhook_secret': settings.RAZORPAY_WEBHOOK_SECRET,
        }

    raise PaymentAccountNotConfigured(
        f"No Razorpay account configured for property "
        f"{getattr(property_obj, 'name', None)}."
    )


def _client(creds):
    return razorpay.Client(auth=(creds['key_id'], creds['key_secret']))


def create_razorpay_order(creds, *, amount, currency='INR', receipt=''):
    return _client(creds).order.create({
        'amount': int(amount * 100),   # rupees -> paise
        'currency': currency,
        'receipt': receipt,
        'payment_capture': 1,
    })


def verify_payment_signature(creds, *, razorpay_order_id, razorpay_payment_id, razorpay_signature):
    try:
        _client(creds).utility.verify_payment_signature({
            'razorpay_order_id': razorpay_order_id,
            'razorpay_payment_id': razorpay_payment_id,
            'razorpay_signature': razorpay_signature,
        })
        return True
    except razorpay.errors.SignatureVerificationError:
        return False


def verify_webhook_signature(creds, *, payload_body, signature):
    secret = creds.get('webhook_secret') or ''
    if not secret:
        return False   # never accept unsigned webhooks
    expected = hmac.new(secret.encode(), payload_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)