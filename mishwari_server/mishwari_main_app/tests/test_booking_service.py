"""Tests for booking service"""

from django.test import TestCase
from django.contrib.auth.models import User
from ..services.booking_service import BookingService, InsufficientSeatsError
from ..models import Trip, TripStop, CityList, BusOperator, Bus, Driver, Profile


class BookingServiceTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('testuser')
        Profile.objects.create(user=self.user, mobile_number='1234567890')
        
        self.operator = BusOperator.objects.create(name='Test Operator', contact_info='test@test.com')
        self.bus = Bus.objects.create(operator=self.operator, bus_number='TEST123', bus_type='Standard', capacity=40)
        
        self.from_city = CityList.objects.create(city='CityA')
        self.to_city = CityList.objects.create(city='CityB')
        
        self.trip = Trip.objects.create(
            operator=self.operator,
            bus=self.bus,
            from_city=self.from_city,
            to_city=self.to_city,
            journey_date='2024-01-01',
            planned_polyline='test',
            status='published'
        )
        
        self.from_stop = TripStop.objects.create(
            trip=self.trip,
            city=self.from_city,
            sequence=0,
            planned_arrival='2024-01-01 08:00:00',
            planned_departure='2024-01-01 08:00:00',
            price_from_start=0
        )
        
        self.to_stop = TripStop.objects.create(
            trip=self.trip,
            city=self.to_city,
            sequence=1,
            planned_arrival='2024-01-01 10:00:00',
            planned_departure='2024-01-01 10:00:00',
            distance_from_start_km=100,
            price_from_start=500
        )
        
        self.trip.seat_matrix = {'0-1': 40}
        self.trip.save()
    
    def test_create_booking_success(self):
        service = BookingService()
        passengers = [{'name': 'Test Passenger', 'age': 25, 'gender': 'male', 'is_checked': True}]
        
        booking = service.create_booking(
            trip_id=self.trip.id,
            from_stop_id=self.from_stop.id,
            to_stop_id=self.to_stop.id,
            user=self.user,
            passengers_data=passengers
        )
        
        self.assertIsNotNone(booking)
        self.assertEqual(booking.total_fare, 500)
        self.assertEqual(len(booking.passengers_data), 1)
    
    def test_create_booking_insufficient_seats(self):
        self.trip.seat_matrix = {'0-1': 0}
        self.trip.save()
        
        service = BookingService()
        passengers = [{'name': 'Test', 'age': 25, 'is_checked': True}]
        
        with self.assertRaises(InsufficientSeatsError):
            service.create_booking(
                trip_id=self.trip.id,
                from_stop_id=self.from_stop.id,
                to_stop_id=self.to_stop.id,
                user=self.user,
                passengers_data=passengers
            )
