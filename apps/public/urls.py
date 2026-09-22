from django.urls import path
from .views import (
    landing_page, search_results, booking_form, confirmation, view_invoice,
    send_booking_otp, verify_booking_otp,
)

app_name = 'public'

urlpatterns = [
    path('', landing_page, name='landing'),
    path('book/search/', search_results, name='search'),
    path('book/form/', booking_form, name='book'),
    path('book/confirmation/<str:booking_number>/', confirmation, name='confirmation'),
    path('book/invoice/<str:booking_number>/', view_invoice, name='invoice'),
    path('book/otp/send/', send_booking_otp, name='send_otp'),
    path('book/otp/verify/', verify_booking_otp, name='verify_otp'),
]