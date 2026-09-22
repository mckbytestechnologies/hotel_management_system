import razorpay
import hmac
import hashlib
from django.conf import settings


def get_client():
    return razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


def create_razorpay_order(*, amount, currency='INR', receipt=''):
    """
    Creates a Razorpay order for the given amount (in rupees — converted
    to paise here since Razorpay's API expects the smallest currency unit).
    Returns the order dict, which the frontend uses to open Razorpay's
    checkout widget.
    """
    client = get_client()
    order = client.order.create({
        'amount': int(amount * 100),  # rupees -> paise
        'currency': currency,
        'receipt': receipt,
        'payment_capture': 1,  # auto-capture on successful payment
    })
    return order


def verify_payment_signature(*, razorpay_order_id, razorpay_payment_id, razorpay_signature):
    """
    Verifies the signature Razorpay sends back after checkout completes,
    proving the payment response wasn't tampered with client-side.
    Returns True/False rather than raising, so the caller decides how
    to handle a failed verification.
    """
    client = get_client()
    try:
        client.utility.verify_payment_signature({
            'razorpay_order_id': razorpay_order_id,
            'razorpay_payment_id': razorpay_payment_id,
            'razorpay_signature': razorpay_signature,
        })
        return True
    except razorpay.errors.SignatureVerificationError:
        return False


def verify_webhook_signature(*, payload_body, signature):
    """
    Verifies a Razorpay webhook's signature using the webhook secret
    (different from the API secret) configured in the Razorpay dashboard.
    payload_body must be the raw request body bytes, not parsed JSON —
    HMAC verification requires the exact bytes Razorpay signed.
    """
    expected_signature = hmac.new(
        key=settings.RAZORPAY_WEBHOOK_SECRET.encode(),
        msg=payload_body,
        digestmod=hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected_signature, signature)