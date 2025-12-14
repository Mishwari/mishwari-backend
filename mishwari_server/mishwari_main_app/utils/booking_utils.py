"""
Booking utilities - DEPRECATED: Use services.booking_service instead
Kept for backward compatibility
"""
from ..services.booking_service import (
    BookingService,
    InsufficientSeatsError,
    BookingAlreadyCancelledError
)

# Backward compatibility exports
__all__ = ['InsufficientSeatsError', 'BookingAlreadyCancelledError', 'create_booking_atomic', 'cancel_booking_atomic']


def create_booking_atomic(trip_id, from_stop_id, to_stop_id, user, passengers_data, payment_method='cash', contact_name=None, contact_phone=None, contact_email=None):
    """DEPRECATED: Use BookingService().create_booking() instead"""
    service = BookingService()
    return service.create_booking(
        trip_id=trip_id,
        from_stop_id=from_stop_id,
        to_stop_id=to_stop_id,
        user=user,
        passengers_data=passengers_data,
        payment_method=payment_method,
        contact_name=contact_name,
        contact_phone=contact_phone,
        contact_email=contact_email
    )


def cancel_booking_atomic(booking_id):
    """DEPRECATED: Use BookingService().cancel_booking() instead"""
    service = BookingService()
    return service.cancel_booking(booking_id)


def get_available_seats_for_segments(trip, segments, count):
    """DEPRECATED: Use BookingService()._get_available_seats_for_segments() instead"""
    service = BookingService()
    return service._get_available_seats_for_segments(trip, segments, count)


def calculate_stop_prices(stops_data, price_per_km=50):
    """
    Auto-calculate prices for stops based on distance
    Driver can override with custom_price
    
    Args:
        stops_data: List of dicts with distance_from_start_km and optional custom_price
        price_per_km: Price per kilometer (default 50)
    
    Returns:
        List of prices (cumulative from start)
    """
    
    prices = []
    for i, stop in enumerate(stops_data):
        if i == 0:
            prices.append(0)  # Origin = 0
        else:
            distance = stop.get('distance_from_start_km', 0)
            auto_price = int(distance * price_per_km)
            
            # Driver can override
            final_price = stop.get('custom_price', auto_price)
            prices.append(final_price)
    
    return prices


def get_available_seats_for_journey(trip, from_stop, to_stop):
    """DEPRECATED: Use BookingService().get_available_seats_for_journey() instead"""
    service = BookingService()
    return service.get_available_seats_for_journey(trip, from_stop, to_stop)
