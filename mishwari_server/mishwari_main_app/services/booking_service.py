"""Booking service - business logic for booking operations"""

from django.db import transaction
from django.utils import timezone
from ..models import Trip, TripStop, Booking, Seat
from ..utils.constants import BookingStatus, BusinessRules


class InsufficientSeatsError(Exception):
    """Raised when not enough seats available"""
    pass


class BookingAlreadyCancelledError(Exception):
    """Raised when trying to cancel already cancelled booking"""
    pass


class BookingService:
    """Service for booking operations"""
    
    @transaction.atomic
    def create_booking(self, trip_id, from_stop_id, to_stop_id, user, passengers_data, 
                      payment_method='cash', contact_name=None, contact_phone=None, contact_email=None):
        """
        Create booking with atomic seat reduction
        
        Args:
            trip_id: Trip ID
            from_stop_id: Starting TripStop ID
            to_stop_id: Ending TripStop ID
            user: User object
            passengers_data: List of passenger dicts
            payment_method: Payment method choice
            
        Returns:
            Booking object
            
        Raises:
            InsufficientSeatsError: If not enough seats available
        """
        trip = Trip.objects.select_for_update().get(id=trip_id)
        from_stop = TripStop.objects.get(id=from_stop_id, trip=trip)
        to_stop = TripStop.objects.get(id=to_stop_id, trip=trip)
        
        segments = [f"{i}-{i+1}" for i in range(from_stop.sequence, to_stop.sequence)]
        checked_passengers = [p for p in passengers_data if p.get('is_checked', True)]
        passenger_count = len(checked_passengers)
        
        if not trip.seat_matrix:
            raise InsufficientSeatsError("Seat matrix not initialized")
        
        min_seats = min(trip.seat_matrix.get(seg, 0) for seg in segments)
        if min_seats < passenger_count:
            raise InsufficientSeatsError(f"Only {min_seats} seats available")
        
        # Reduce seats atomically
        for seg in segments:
            trip.seat_matrix[seg] -= passenger_count
        trip.save()
        
        fare = (to_stop.price_from_start - from_stop.price_from_start) * passenger_count
        available_seats = self._get_available_seats_for_segments(trip, segments, passenger_count)
        
        passengers_with_seats = []
        for i, passenger_data in enumerate(checked_passengers):
            seat = available_seats[i] if i < len(available_seats) else None
            passengers_with_seats.append({
                'name': passenger_data.get('name'),
                'age': passenger_data.get('age'),
                'gender': passenger_data.get('gender'),
                'seat_number': seat.seat_number if seat else None
            })
            
            if seat:
                seat.available_segments = [s for s in seat.available_segments if s not in segments]
                seat.save()
        
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
            status=BookingStatus.CONFIRMED,
            payment_method=payment_method,
            is_paid=False
        )
        
        return booking
    
    @transaction.atomic
    def cancel_booking(self, booking_id):
        """Cancel booking and restore seats atomically"""
        booking = Booking.objects.select_related('trip').get(id=booking_id)
        
        if booking.status == BookingStatus.CANCELLED:
            raise BookingAlreadyCancelledError("Booking already cancelled")
        
        trip = Trip.objects.select_for_update().get(id=booking.trip.id)
        segments = booking.get_crossed_segments()
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
        
        booking.status = BookingStatus.CANCELLED
        booking.cancelled_at = timezone.now()
        booking.save()
        
        return booking
    
    def get_available_seats_for_journey(self, trip, from_stop, to_stop):
        """Get available seats for a journey between two stops"""
        if not trip.seat_matrix:
            return 0
        
        segments = [f"{i}-{i+1}" for i in range(from_stop.sequence, to_stop.sequence)]
        return min(trip.seat_matrix.get(seg, 0) for seg in segments) if segments else 0
    
    def _get_available_seats_for_segments(self, trip, segments, count):
        """Get available seats for given segments"""
        all_seats = Seat.objects.filter(trip=trip)
        available = []
        
        for seat in all_seats:
            if len(available) >= count:
                break
            if seat.is_available_for_segments(segments):
                available.append(seat)
        
        return available
