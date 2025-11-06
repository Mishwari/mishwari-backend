"""
Script to update existing data after model changes
Run this after migrations: python manage.py shell < update_existing_data.py
"""

from mishwari_main_app.models import Profile, Trip, Booking

# Update all existing profiles to passenger role
Profile.objects.filter(role__isnull=True).update(role='passenger')
print(f"Updated {Profile.objects.filter(role='passenger').count()} profiles to passenger role")

# Update all existing trips to scheduled type
Trip.objects.filter(trip_type__isnull=True).update(trip_type='scheduled')
print(f"Updated {Trip.objects.filter(trip_type='scheduled').count()} trips to scheduled type")

# Update all existing bookings to platform source
Booking.objects.filter(booking_source__isnull=True).update(booking_source='platform')
print(f"Updated {Booking.objects.filter(booking_source='platform').count()} bookings to platform source")

print("Data migration completed successfully!")
