"""
Booking utilities with atomic operations and race condition protection
"""
from django.db import transaction
from django.utils import timezone
from .models import Trip, TripStop, Booking, Passenger, Seat


class InsufficientSeatsError(Exception):
    """Raised when not enough seats available"""
    pass


class BookingAlreadyCancelledError(Exception):
    """Raised when trying to cancel already cancelled booking"""
    pass


@transaction.atomic
def create_booking_atomic(trip_id, from_stop_id, to_stop_id, user, passengers_data, payment_method='cash', contact_name=None, contact_phone=None, contact_email=None):
    """
    Create booking with atomic seat reduction (prevents race conditions)
    
    Args:
        trip_id: Trip ID
        from_stop_id: Starting TripStop ID
        to_stop_id: Ending TripStop ID
        user: User object
        passengers_data: List of passenger dicts with name, age, gender
        payment_method: Payment method choice
    
    Returns:
        Booking object
    
    Raises:
        InsufficientSeatsError: If not enough seats available
    """
    
    # Lock the trip row (prevents concurrent modifications)
    trip = Trip.objects.select_for_update().get(id=trip_id)
    
    # Get stops
    from_stop = TripStop.objects.get(id=from_stop_id, trip=trip)
    to_stop = TripStop.objects.get(id=to_stop_id, trip=trip)
    
    # Calculate crossed segments
    segments = [f"{i}-{i+1}" for i in range(from_stop.sequence, to_stop.sequence)]
    
    # Filter only checked passengers for booking (if is_checked field exists)
    # For physical bookings, all passengers are considered checked
    checked_passengers = [p for p in passengers_data if p.get('is_checked', True)]
    passenger_count = len(checked_passengers)
    
    if not trip.seat_matrix:
        raise InsufficientSeatsError("Seat matrix not initialized")
    
    # Check segment-based availability
    min_seats = min(trip.seat_matrix.get(seg, 0) for seg in segments)
    
    if min_seats < passenger_count:
        raise InsufficientSeatsError(f"Only {min_seats} seats available")
    
    # Reduce seats atomically
    for seg in segments:
        trip.seat_matrix[seg] -= passenger_count
    
    trip.save()
    
    # Calculate fare based on checked passengers
    fare = (to_stop.price_from_start - from_stop.price_from_start) * len(checked_passengers)
    
    # Get available seats and assign to passengers
    available_seats = get_available_seats_for_segments(trip, segments, passenger_count)
    
    # Build passengers data with seat assignments
    passengers_with_seats = []
    for i, passenger_data in enumerate(checked_passengers):
        seat = available_seats[i] if i < len(available_seats) else None
        
        passenger_snapshot = {
            'name': passenger_data.get('name'),
            'age': passenger_data.get('age'),
            'gender': passenger_data.get('gender'),
            'seat_number': seat.seat_number if seat else None
        }
        passengers_with_seats.append(passenger_snapshot)
        
        # Remove segments from seat availability
        if seat:
            seat.available_segments = [s for s in seat.available_segments if s not in segments]
            seat.save()
    
    # Create booking with passenger data
    booking = Booking.objects.create(
        user=user,
        trip=trip,
        from_stop=from_stop,
        to_stop=to_stop,
        passengers_data=passengers_with_seats,
        contact_name=contact_name,
        contact_phone=contact_phone,
        contact_email=contact_email,
        total_fare=fare,
        status='confirmed',
        payment_method=payment_method,
        is_paid=False
    )
    
    return booking


@transaction.atomic
def cancel_booking_atomic(booking_id):
    """
    Cancel booking and restore seats atomically
    
    Args:
        booking_id: Booking ID
    
    Returns:
        Booking object
    
    Raises:
        BookingAlreadyCancelledError: If booking already cancelled
    """
    
    booking = Booking.objects.select_related('trip').get(id=booking_id)
    
    if booking.status == 'cancelled':
        raise BookingAlreadyCancelledError("Booking already cancelled")
    
    # Lock trip
    trip = Trip.objects.select_for_update().get(id=booking.trip.id)
    
    # Calculate segments
    segments = booking.get_crossed_segments()
    
    # Restore seats
    passenger_count = len(booking.passengers_data)
    
    for seg in segments:
        trip.seat_matrix[seg] = trip.seat_matrix.get(seg, 0) + passenger_count
    
    trip.save()
    
    # Release seat assignments
    for passenger in booking.passengers_data:
        seat_number = passenger.get('seat_number')
        if seat_number:
            seat = Seat.objects.filter(trip=trip, seat_number=seat_number).first()
            if seat:
                seat.available_segments.extend(segments)
                seat.save()
    
    # Update booking status
    booking.status = 'cancelled'
    booking.cancelled_at = timezone.now()
    booking.save()
    
    return booking


def get_available_seats_for_segments(trip, segments, count):
    """
    Get available seats for given segments
    
    Args:
        trip: Trip object
        segments: List of segment strings like ["0-1", "1-2"]
        count: Number of seats needed
    
    Returns:
        List of Seat objects
    """
    
    # Get all seats for this trip
    all_seats = Seat.objects.filter(trip=trip)
    
    available = []
    for seat in all_seats:
        if len(available) >= count:
            break
        if seat.is_available_for_segments(segments):
            available.append(seat)
    
    return available


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
    """
    Get available seats for a journey between two stops
    
    Args:
        trip: Trip object
        from_stop: Starting TripStop object
        to_stop: Ending TripStop object
    
    Returns:
        int: Number of available seats
    """
    
    if not trip.seat_matrix:
        return 0
    
    # Calculate segments
    segments = [f"{i}-{i+1}" for i in range(from_stop.sequence, to_stop.sequence)]
    
    # Return minimum across all segments
    return min(trip.seat_matrix.get(seg, 0) for seg in segments) if segments else 0
