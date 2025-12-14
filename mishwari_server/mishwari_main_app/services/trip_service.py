"""Trip service - business logic for trip operations"""

from django.db import transaction
from django.utils import timezone
from ..models import Trip, TripStop, CityList
from ..utils.constants import TripStatus


class TripService:
    """Service for trip operations"""
    
    def search_trips(self, from_city_name, to_city_name, date):
        """Search trips between cities on a specific date"""
        try:
            from_city = CityList.objects.get(city=from_city_name)
            to_city = CityList.objects.get(city=to_city_name)
        except CityList.DoesNotExist:
            return []
        
        trips_with_from = TripStop.objects.filter(
            city=from_city,
            trip__journey_date=date,
            trip__status=TripStatus.PUBLISHED
        ).values_list('trip_id', flat=True)
        
        trips_with_to = TripStop.objects.filter(
            city=to_city,
            trip__journey_date=date,
            trip__status=TripStatus.PUBLISHED
        ).values_list('trip_id', flat=True)
        
        matching_trip_ids = set(trips_with_from) & set(trips_with_to)
        
        results = []
        for trip_id in matching_trip_ids:
            trip = Trip.objects.select_related('bus', 'driver', 'operator').get(id=trip_id)
            from_stop = trip.stops.filter(city=from_city).first()
            to_stop = trip.stops.filter(city=to_city).first()
            
            if not from_stop or not to_stop or from_stop.sequence >= to_stop.sequence:
                continue
            
            segments = [f"{i}-{i+1}" for i in range(from_stop.sequence, to_stop.sequence)]
            available_seats = min([trip.seat_matrix.get(seg, 0) for seg in segments]) if segments else 0
            fare = to_stop.price_from_start - from_stop.price_from_start
            
            results.append({
                'trip': trip,
                'from_stop': from_stop,
                'to_stop': to_stop,
                'available_seats': available_seats,
                'fare': fare
            })
        
        return results
    
    @transaction.atomic
    def publish_trip(self, trip_id):
        """Publish a draft trip with validation"""
        trip = Trip.objects.select_for_update().get(id=trip_id)
        
        if trip.status != TripStatus.DRAFT:
            raise ValueError('Only draft trips can be published')
        
        trip.status = TripStatus.PUBLISHED
        trip.full_clean()
        trip.save()
        
        return trip
    
    @transaction.atomic
    def activate_trip(self, trip_id):
        """Activate trip (departure)"""
        trip = Trip.objects.select_for_update().get(id=trip_id)
        
        if trip.status != TripStatus.PUBLISHED:
            raise ValueError('Only published trips can be activated')
        
        trip.actual_departure = timezone.now()
        trip.status = TripStatus.ACTIVE
        trip.save()
        
        return trip
    
    @transaction.atomic
    def complete_trip(self, trip_id):
        """Mark trip as completed"""
        from ..models import Booking
        from ..utils.constants import BookingStatus
        
        trip = Trip.objects.select_for_update().get(id=trip_id)
        
        if trip.status not in [TripStatus.ACTIVE, TripStatus.PUBLISHED]:
            raise ValueError(f'Cannot complete trip with status "{trip.status}"')
        
        trip.status = TripStatus.COMPLETED
        trip.completed_at = timezone.now()
        trip.save()
        
        bookings = Booking.objects.filter(trip=trip).exclude(
            status__in=[BookingStatus.CANCELLED, BookingStatus.COMPLETED]
        )
        completed_count = bookings.update(status=BookingStatus.COMPLETED)
        
        return trip, completed_count
