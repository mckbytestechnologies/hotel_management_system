from django.urls import path
from .views import landing_page, search_results, booking_form, confirmation

app_name = 'public'

urlpatterns = [
    path('', landing_page, name='landing'),
    path('book/search/', search_results, name='search'),
    path('book/form/', booking_form, name='book'),
    path('book/confirmation/<str:booking_number>/', confirmation, name='confirmation'),
]