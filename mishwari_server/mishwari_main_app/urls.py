from django.urls import path,include
from rest_framework import routers

from django.contrib.auth.models import User

from .views import (
    TripsViewSet, DriverView, TripStopView, JwtUserView,
    DriverTripView, JwtDriverView, RouteViewSet,
    TripSearchView, CitiesView, BookingViewSet, BookingTripsViewSet, PassengersViewSet,
    TripReviewViewSet, stripe_webhook,
    OperatorFleetViewSet, OperatorTripViewSet, PhysicalBookingViewSet,
    DriverManagementViewSet, UpgradeRequestViewSet,
    MobileLoginView, whatsapp_webhook, ProfileView
)

router = routers.DefaultRouter()
# router.register(r"users", UserViewSet)
router.register(r"drivers", DriverView)
router.register(r"trips", TripSearchView, basename='trips')  # Main trip search endpoint
router.register(r"trip-stops", TripStopView, basename='trip-stops')

router.register(r"user",JwtUserView, basename="jwt-user")
router.register(r"driver-details",JwtDriverView, basename="driver-details")
router.register(r"driver-trips",DriverTripView, basename="driver-trips")

router.register(r"route",RouteViewSet,basename="route")

router.register(r"test-create", TripsViewSet,basename="test-create")
router.register(r"city-list",CitiesView,basename="city-list")
router.register(r"booking",BookingViewSet,basename="booking")
router.register(r"seats",BookingTripsViewSet,basename="seats")
router.register(r"passengers",PassengersViewSet, basename="user-passengers")
router.register(r"reviews", TripReviewViewSet, basename="reviews")
router.register(r"mobile-login",MobileLoginView, basename="mobile-login")
router.register(r"profile",ProfileView,basename="profile")

# Operator endpoints
router.register(r"operator/fleet", OperatorFleetViewSet, basename="operator-fleet")
router.register(r"operator/trips", OperatorTripViewSet, basename="operator-trips")
router.register(r"operator/physical-bookings", PhysicalBookingViewSet, basename="operator-physical-bookings")
router.register(r"operator/drivers", DriverManagementViewSet, basename="operator-drivers")
router.register(r"operator/upgrade", UpgradeRequestViewSet, basename="operator-upgrade")

urlpatterns = [
    path('', include(router.urls)),
    path('api-auth/', include('rest_framework.urls')),    # to login in rest_framework
    path('webhook/stripe/', stripe_webhook, name='stripe-webhook'),
    path('whatsapp-response/', whatsapp_webhook.as_view(), name='whatsapp-response'),

]

