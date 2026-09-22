from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import (
    BookingViewSet, create_payment_order, verify_payment,
    RazorpayWebhookView, get_invoice,
)

router = DefaultRouter()
router.register(r'bookings', BookingViewSet, basename='booking')

urlpatterns = [
    path('bookings/create-payment-order/', create_payment_order, name='create-payment-order'),
    path('bookings/verify-payment/', verify_payment, name='verify-payment'),
    path('bookings/razorpay-webhook/', RazorpayWebhookView.as_view(), name='razorpay-webhook'),
    path('bookings/invoice/<str:booking_number>/', get_invoice, name='get-invoice'),
] + router.urls