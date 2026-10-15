from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError
from django.conf import settings
from apps.properties.models import Property
from apps.guests.models import Guest
from .models import Booking
from .serializers import BookingSerializer, BookingCreateSerializer
from .services import create_booking, RoomNotAvailableError
from .services import (
    create_booking, RoomNotAvailableError,
    check_in_booking, check_out_booking, InvalidBookingStateError,
)
import json
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.views import View
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from .razorpay_client import (
    get_credentials, PaymentAccountNotConfigured,
    create_razorpay_order, verify_payment_signature, verify_webhook_signature,
)
from .services import record_payment
from .models import Payment
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from django.utils import timezone
from .services import generate_invoice
from .models import Invoice
from .services import send_booking_confirmation_email, send_admin_booking_notification


class BookingViewSet(viewsets.ModelViewSet):
    queryset = Booking.objects.select_related('guest', 'property').prefetch_related(
        'booking_rooms__room', 'booking_rooms__room_type', 'booking_rooms__rate_plan'
    ).all()
    serializer_class = BookingSerializer
    filterset_fields = ['property', 'status', 'source', 'guest']

    def create(self, request, *args, **kwargs):
        input_serializer = BookingCreateSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        data = input_serializer.validated_data

        property_obj = get_object_or_404(Property, id=data['property'])
        guest = get_object_or_404(Guest, id=data['guest'])

        try:
            booking = create_booking(
                property_obj=property_obj,
                guest=guest,
                check_in_date=data['check_in_date'],
                check_out_date=data['check_out_date'],
                room_requests=data['rooms'],
                source=data['source'],
                adults=data['adults'],
                children=data['children'],
                special_requests=data['special_requests'],
            )
        except RoomNotAvailableError as e:
            return Response({'detail': str(e)}, status=status.HTTP_409_CONFLICT)
        except ValidationError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(BookingSerializer(booking).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """POST /api/bookings/{id}/cancel/ — releases the room inventory back."""
        booking = self.get_object()
        if booking.status == Booking.Status.CANCELLED:
            return Response({'detail': 'Booking is already cancelled.'}, status=400)

        from django.utils import timezone
        from apps.availability.models import Availability

        Availability.objects.filter(
            booking_room__booking=booking
        ).update(is_available=True, booking_room=None)

        booking.status = Booking.Status.CANCELLED
        booking.cancelled_at = timezone.now()
        booking.cancellation_reason = request.data.get('reason', '')
        booking.save(update_fields=['status', 'cancelled_at', 'cancellation_reason', 'updated_at'])

        return Response(BookingSerializer(booking).data)

    @action(detail=True, methods=['post'])
    def check_in(self, request, pk=None):
        try:
            booking = check_in_booking(pk)
        except InvalidBookingStateError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(BookingSerializer(booking).data)

    @action(detail=True, methods=['post'])
    def check_out(self, request, pk=None):
        try:
            booking = check_out_booking(pk)
        except InvalidBookingStateError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(BookingSerializer(booking).data)

from rest_framework.authentication import SessionAuthentication


class CsrfExemptSessionAuthentication(SessionAuthentication):
    """
    DRF's SessionAuthentication enforces CSRF even when permission_classes
    allows anonymous access — these two payment endpoints are called from
    the public (unauthenticated) booking confirmation page via plain
    fetch(), so they need CSRF exemption. Security here relies on
    Razorpay's own signature verification, not CSRF/session auth.
    """
    def enforce_csrf(self, request):
        return  # skip CSRF check


@api_view(['POST'])
@authentication_classes([CsrfExemptSessionAuthentication])
@permission_classes([AllowAny])
def create_payment_order(request):
    booking = get_object_or_404(Booking, id=request.data.get('booking_id'))
    amount = request.data.get('amount') or booking.balance_due()

    if amount <= 0:
        return Response({'detail': 'Nothing due to pay.'}, status=400)

    try:
        creds = get_credentials(booking.property)
    except PaymentAccountNotConfigured as e:
        return Response({'detail': str(e)}, status=503)

    order = create_razorpay_order(creds, amount=amount, receipt=booking.booking_number)

    payment = Payment.objects.create(
        booking=booking, amount=amount,
        method=Payment.Method.ONLINE_GATEWAY,
        status=Payment.Status.PENDING,
        gateway_order_id=order['id'],
    )

    return Response({
        'razorpay_order_id': order['id'],
        'razorpay_key_id': creds['key_id'],      # this property's key, not a global one
        'amount': order['amount'],
        'currency': order['currency'],
        'payment_id': payment.id,
        'booking_number': booking.booking_number,
    })


@api_view(['POST'])
@authentication_classes([CsrfExemptSessionAuthentication])
@permission_classes([AllowAny])
def verify_payment(request):
    order_id = request.data.get('razorpay_order_id')
    payment_id = request.data.get('razorpay_payment_id')
    signature = request.data.get('razorpay_signature')

    if not all([order_id, payment_id, signature]):
        return Response({'detail': 'Missing verification fields.'}, status=400)

    # Find the payment first: it tells us which property's keys to verify with.
    payment = get_object_or_404(Payment.objects.select_related('booking__property'), gateway_order_id=order_id)
    booking = payment.booking

    try:
        creds = get_credentials(booking.property)
    except PaymentAccountNotConfigured as e:
        return Response({'detail': str(e)}, status=503)

    if not verify_payment_signature(
        creds, razorpay_order_id=order_id,
        razorpay_payment_id=payment_id, razorpay_signature=signature,
    ):
        return Response({'detail': 'Payment signature verification failed.'}, status=400)

    if payment.status == Payment.Status.SUCCESS:
        return Response({'detail': 'Payment already verified.'})

    payment.status = Payment.Status.SUCCESS
    payment.transaction_reference = payment_id
    payment.paid_at = timezone.now()
    payment.save(update_fields=['status', 'transaction_reference', 'paid_at', 'updated_at'])

    booking.paid_amount = booking.paid_amount + payment.amount
    booking.save(update_fields=['paid_amount', 'updated_at'])

    invoice = generate_invoice(booking.id)
    send_booking_confirmation_email(booking)
    send_admin_booking_notification(booking)

    return Response({
        'detail': 'Payment verified successfully.',
        'booking_number': booking.booking_number,
        'invoice_number': invoice.invoice_number,
    })


@method_decorator(csrf_exempt, name='dispatch')
class RazorpayWebhookView(View):
    """
    One webhook URL per property:  /api/bookings/razorpay-webhook/<property_id>/
    Each Razorpay account signs with its own secret, so the property in the
    URL decides which secret is used to verify the request.
    """
    def post(self, request, property_id=None):
        from django.http import JsonResponse

        property_obj = Property.objects.filter(id=property_id).first() if property_id else None
        if property_id and not property_obj:
            return JsonResponse({'detail': 'Unknown property'}, status=404)

        try:
            creds = get_credentials(property_obj)
        except PaymentAccountNotConfigured:
            return JsonResponse({'detail': 'Payment account not configured'}, status=503)

        signature = request.headers.get('X-Razorpay-Signature', '')
        if not verify_webhook_signature(creds, payload_body=request.body, signature=signature):
            return JsonResponse({'detail': 'Invalid signature'}, status=400)

        payload = json.loads(request.body)
        event = payload.get('event')

        if event == 'payment.captured':
            entity = payload['payload']['payment']['entity']
            payment = Payment.objects.select_related('booking').filter(
                gateway_order_id=entity.get('order_id')
            ).first()

            # A webhook for property A must never mark property B's payment paid.
            if payment and property_obj and payment.booking.property_id != property_obj.id:
                return JsonResponse({'detail': 'Property mismatch'}, status=400)

            if payment and payment.status != Payment.Status.SUCCESS:
                payment.status = Payment.Status.SUCCESS
                payment.transaction_reference = entity.get('id')
                payment.paid_at = timezone.now()
                payment.save(update_fields=['status', 'transaction_reference', 'paid_at', 'updated_at'])

                booking = payment.booking
                booking.paid_amount = booking.paid_amount + payment.amount
                booking.save(update_fields=['paid_amount', 'updated_at'])
                generate_invoice(booking.id)
                send_booking_confirmation_email(booking)
                send_admin_booking_notification(booking)

        elif event == 'payment.failed':
            entity = payload['payload']['payment']['entity']
            Payment.objects.filter(
                gateway_order_id=entity.get('order_id')
            ).exclude(status=Payment.Status.SUCCESS).update(status=Payment.Status.FAILED)

        return JsonResponse({'status': 'ok'})

        
@api_view(['GET'])
@permission_classes([AllowAny])
def get_invoice(request, booking_number):
    """GET /api/bookings/invoice/{booking_number}/ — fetch (or lazily generate) the invoice."""
    booking = get_object_or_404(Booking, booking_number=booking_number)
    invoice = Invoice.objects.filter(booking=booking).first()
    if not invoice:
        invoice = generate_invoice(booking.id)

    return Response({
        'invoice_number': invoice.invoice_number,
        'booking_number': booking.booking_number,
        'guest_name': booking.guest.full_name,
        'property_name': booking.property.name,
        'issued_at': invoice.issued_at,
        'line_items': invoice.line_items,
        'subtotal': invoice.subtotal,
        'tax_amount': invoice.tax_amount,
        'discount_amount': invoice.discount_amount,
        'total_amount': invoice.total_amount,
    })