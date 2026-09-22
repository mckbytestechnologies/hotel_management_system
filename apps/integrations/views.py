import json
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.http import JsonResponse

from apps.properties.models import Property
from .models import ChannelMapping
from .channex_client import handle_channex_booking_webhook


@method_decorator(csrf_exempt, name='dispatch')
class ChannexWebhookView(View):
    """
    Channex calls this URL whenever a booking/ari/sync_error event occurs
    for any property connected via our API key. We validate the secret,
    then route booking events into our existing atomic booking pipeline.
    """
    def post(self, request):
        secret = request.headers.get('X-Webhook-Secret', '')
        from django.conf import settings
        if settings.CHANNEX_WEBHOOK_SECRET and secret != settings.CHANNEX_WEBHOOK_SECRET:
            return JsonResponse({'detail': 'Invalid webhook secret'}, status=401)

        payload = json.loads(request.body)
        event = payload.get('event')

        # TEMPORARY: log every webhook call raw, so we can see Channex's
        # actual payload shape before wiring the real handler logic.
        print("=== CHANNEX WEBHOOK RECEIVED ===")
        print("Event:", event)
        print("Full payload:", json.dumps(payload, indent=2))
        print("=================================")

        if event == 'booking':
            handle_channex_booking_webhook(payload)

        return JsonResponse({'status': 'ok'})