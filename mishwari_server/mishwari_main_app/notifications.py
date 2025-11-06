from django.utils import timezone
from .models import Trip, Booking

def send_departure_notification(trip_id):
    """Send SMS/Push notification when flexible trip departs"""
    trip = Trip.objects.get(id=trip_id)
    bookings = Booking.objects.filter(trip=trip, status='confirmed')
    
    for booking in bookings:
        message = f"Your shuttle to {trip.to_city.city} is departing in 10 minutes. Please board Bus {trip.bus.bus_number} now."
        # TODO: Integrate with Infobip SMS API (already exists in project)
        # TODO: Integrate with Push Notification service
        print(f"Notification sent to {booking.user.username}: {message}")
    
    trip.actual_departure = timezone.now()
    trip.save()
    
    return len(bookings)
