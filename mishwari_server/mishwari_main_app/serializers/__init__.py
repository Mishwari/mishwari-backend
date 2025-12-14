"""Serializers package - imports from domain-specific modules"""

# User serializers
from .user_serializers import (
    UserSerializer,
    ProfileSerializer,
    ProfileCompletionSerializer,
)

# Operator and fleet serializers
from .operator_serializers import (
    BusOperatorSerializer,
    BusSerializer,
    DriverSerializer,
)

# Trip serializers
from .trip_serializers import (
    CitiesSerializer,
    TripsSerializer,
    TripStopSerializer,
    SeatSerializer,
)

# Booking serializers
from .booking_serializers import (
    BookingTripSerializer,
    PassengerSerializer,
    BookingSerializer,
)

# Review serializers
from .review_serializers import (
    TripReviewSerializer,
)

__all__ = [
    'UserSerializer',
    'ProfileSerializer',
    'ProfileCompletionSerializer',
    'BusOperatorSerializer',
    'BusSerializer',
    'DriverSerializer',
    'CitiesSerializer',
    'TripsSerializer',
    'TripStopSerializer',
    'SeatSerializer',
    'BookingTripSerializer',
    'PassengerSerializer',
    'TripReviewSerializer',
    'BookingSerializer',
]
