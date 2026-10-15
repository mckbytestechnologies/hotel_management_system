from django.urls import path
from .views import (
    landing_page, search_results, booking_form, confirmation, view_invoice,
    send_booking_otp, verify_booking_otp, stays, about, contact,
    privay_policy, termsandcondition, locations, gallery,submit_inquiry,
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
    path('stays/', stays, name='stays'),
    path('about/', about, name='about'),
    path('contact/', contact, name='contact'),
    path('privacy-policy/', privay_policy, name='privacy'),
    path('terms-and-conditions/', termsandcondition, name='terms'),
    path('locations/', locations, name='locations'),
    path('gallery/', gallery, name='gallery'),
    path('inquiry/', submit_inquiry, name='inquiry'),
]