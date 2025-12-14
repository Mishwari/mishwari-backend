"""Models package - domain-based organization"""

# User models
from .user import OTPAttempt, Profile

# Location models
from .location import CityList

# Operator models
from .operator import BusOperator, OperatorMetrics, UpgradeRequest

# Fleet models
from .fleet import Bus, Driver, DriverInvitation

# Trip models
from .trip import Trip, TripStop, Seat

# Booking models
from .booking import Booking, Passenger

# Review models
from .review import TripReview

__all__ = [
    'OTPAttempt', 'Profile', 'CityList', 'BusOperator', 'OperatorMetrics', 'UpgradeRequest',
    'Bus', 'Driver', 'DriverInvitation', 'Trip', 'TripStop', 'Seat', 'Passenger', 'Booking', 'TripReview',
]
