from django.urls import path
from .views import ChannexWebhookView

urlpatterns = [
    path('channex-webhook/', ChannexWebhookView.as_view(), name='channex-webhook'),
]