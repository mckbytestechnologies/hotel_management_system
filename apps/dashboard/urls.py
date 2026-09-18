from django.urls import path
from django.contrib.auth.views import LoginView, LogoutView
from .views import (
    DashboardHomeView,
    PropertyListView, PropertyCreateView, PropertyUpdateView, PropertyDeleteView,
    RoomTypeListView, RoomTypeCreateView, RoomTypeUpdateView, RoomTypeDeleteView,
    RoomListView, RoomCreateView, RoomUpdateView, RoomDeleteView,
    RatePlanListView, RatePlanCreateView, RatePlanUpdateView, RatePlanDeleteView,
    BookingListView, BookingUpdateView,
    RoomRateListView, RoomRateCreateView, RoomRateUpdateView, RoomRateDeleteView,
    BulkRateGenerateView,
)

app_name = 'dashboard'

urlpatterns = [

    path('', DashboardHomeView.as_view(), name='home'),

    path('login/', LoginView.as_view(template_name='dashboard/auth/login.html'), name='login'),
    path('logout/', LogoutView.as_view(next_page='dashboard:login'), name='logout'),

    path('properties/', PropertyListView.as_view(), name='property_list'),
    path('properties/add/', PropertyCreateView.as_view(), name='property_add'),
    path('properties/<int:pk>/edit/', PropertyUpdateView.as_view(), name='property_edit'),
    path('properties/<int:pk>/delete/', PropertyDeleteView.as_view(), name='property_delete'),

    path('room-types/', RoomTypeListView.as_view(), name='roomtype_list'),
    path('room-types/add/', RoomTypeCreateView.as_view(), name='roomtype_add'),
    path('room-types/<int:pk>/edit/', RoomTypeUpdateView.as_view(), name='roomtype_edit'),
    path('room-types/<int:pk>/delete/', RoomTypeDeleteView.as_view(), name='roomtype_delete'),

    path('rooms/', RoomListView.as_view(), name='room_list'),
    path('rooms/add/', RoomCreateView.as_view(), name='room_add'),
    path('rooms/<int:pk>/edit/', RoomUpdateView.as_view(), name='room_edit'),
    path('rooms/<int:pk>/delete/', RoomDeleteView.as_view(), name='room_delete'),

    path('rate-plans/', RatePlanListView.as_view(), name='rateplan_list'),
    path('rate-plans/add/', RatePlanCreateView.as_view(), name='rateplan_add'),
    path('rate-plans/<int:pk>/edit/', RatePlanUpdateView.as_view(), name='rateplan_edit'),
    path('rate-plans/<int:pk>/delete/', RatePlanDeleteView.as_view(), name='rateplan_delete'),

    path('bookings/', BookingListView.as_view(), name='booking_list'),
    path('bookings/<int:pk>/edit/', BookingUpdateView.as_view(), name='booking_edit'),

    path('room-rates/', RoomRateListView.as_view(), name='roomrate_list'),
    path('room-rates/add/', RoomRateCreateView.as_view(), name='roomrate_add'),
    path('room-rates/bulk/', BulkRateGenerateView.as_view(), name='roomrate_bulk'),
    path('room-rates/<int:pk>/edit/', RoomRateUpdateView.as_view(), name='roomrate_edit'),
    path('room-rates/<int:pk>/delete/', RoomRateDeleteView.as_view(), name='roomrate_delete'),
]