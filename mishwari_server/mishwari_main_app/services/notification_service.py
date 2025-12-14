"""Notification service for SMS and push notifications"""
from django.utils import timezone
from ..models import Trip, Booking


class NotificationService:
    def send_departure_notification(self, trip_id):
        """Send SMS/Push notification when flexible trip departs"""
        trip = Trip.objects.get(id=trip_id)
        bookings = Booking.objects.filter(trip=trip, status='confirmed')
        
        for booking in bookings:
            message = f"Your shuttle to {trip.to_city.city} is departing in 10 minutes. Please board Bus {trip.bus.bus_number} now."
            # TODO: Integrate with Infobip SMS API
            # TODO: Integrate with Push Notification service
            print(f"Notification sent to {booking.user.username}: {message}")
        
        trip.actual_departure = timezone.now()
        trip.save()
        
        return len(bookings)
    
    def send_booking_confirmation(self, booking):
        """Send booking confirmation notification"""
        message = f"Booking confirmed for trip to {booking.to_stop.city.city} on {booking.trip.journey_date}"
        # TODO: Implement SMS/Push
        print(f"Confirmation sent to {booking.user.username}: {message}")
    
    def send_cancellation_notification(self, booking):
        """Send booking cancellation notification"""
        message = f"Your booking for trip to {booking.to_stop.city.city} has been cancelled"
        # TODO: Implement SMS/Push
        print(f"Cancellation sent to {booking.user.username}: {message}")
