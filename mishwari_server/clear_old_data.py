"""
Script to clear old data before migration
Run this before migrating to the new system
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mishwari_server.settings')
django.setup()

from mishwari_main_app.models import Seat, Booking, BookingPassenger

print("Clearing old data...")

# Delete all bookings and related data
print(f"Deleting {BookingPassenger.objects.count()} booking passengers...")
BookingPassenger.objects.all().delete()

print(f"Deleting {Booking.objects.count()} bookings...")
Booking.objects.all().delete()

print(f"Deleting {Seat.objects.count()} seats...")
Seat.objects.all().delete()

print("✅ Old data cleared successfully!")
print("Now run: python manage.py migrate")
