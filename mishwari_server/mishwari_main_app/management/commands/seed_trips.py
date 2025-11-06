from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.auth.models import User
from datetime import datetime, timedelta
from mishwari_main_app.models import (
    CityList, BusOperator, Bus, Driver, Trip, TripStop, Seat, Profile, OperatorMetrics
)

class Command(BaseCommand):
    help = 'Seed database with sample trip data for past, current, and future dates'

    def handle(self, *args, **options):
        self.stdout.write('Seeding trip data...')
        
        # Get specific cities: صنعاء، عدن، تعز
        try:
            sanaa = CityList.objects.get(city='صنعاء')
            aden = CityList.objects.get(city='عدن')
            taiz = CityList.objects.get(city='تعز')
            cities = [sanaa, aden, taiz]
        except CityList.DoesNotExist:
            self.stdout.write('Required cities not found. Please run: python manage.py import_cities ./cities_list.json')
            return
        
        # Create operator
        operator, created = BusOperator.objects.get_or_create(
            name='Mishwari Transport',
            defaults={'contact_info': '+967-1-234567', 'uses_own_system': False}
        )
        if created:
            OperatorMetrics.objects.create(operator=operator)
            self.stdout.write(f'Created operator: {operator.name}')

        # Create buses
        buses = []
        for i in range(1, 4):
            bus, created = Bus.objects.get_or_create(
                bus_number=f'YE-{i:03d}',
                defaults={
                    'operator': operator,
                    'bus_type': 'Standard',
                    'capacity': 45,
                    'amenities': {'ac': True, 'wifi': True}
                }
            )
            buses.append(bus)
            if created:
                self.stdout.write(f'Created bus: {bus.bus_number}')

        # Create drivers
        drivers = []
        driver_names = ['Ahmed Ali', 'Mohammed Hassan', 'Omar Saleh']
        for i, name in enumerate(driver_names):
            username = f'driver_{i+1}'
            user, _ = User.objects.get_or_create(username=username)
            profile, _ = Profile.objects.get_or_create(
                user=user,
                defaults={
                    'mobile_number': f'+96777{i+1:07d}',
                    'full_name': name,
                    'role': 'driver',
                    'is_verified': True
                }
            )
            driver, created = Driver.objects.get_or_create(
                user=user,
                defaults={
                    'profile': profile,
                    'operator': operator,
                    'driver_rating': 4.5,
                    'national_id': f'12345678{i+1:02d}'
                }
            )
            if created:
                driver.buses.add(buses[i])
            drivers.append(driver)
            if created:
                self.stdout.write(f'Created driver: {name}')

        # Create trip routes (all combinations)
        routes = [
            (sanaa, aden, 400, 7),    # صنعاء -> عدن
            (sanaa, taiz, 300, 5),    # صنعاء -> تعز
            (aden, sanaa, 400, 7),    # عدن -> صنعاء
            (aden, taiz, 200, 3),     # عدن -> تعز
            (taiz, sanaa, 300, 5),    # تعز -> صنعاء
            (taiz, aden, 200, 3),     # تعز -> عدن
        ]

        trip_count = 0
        now = timezone.now()
        
        # Create trips for next 7 days
        for day_offset in range(0, 7):
            trip_date_dt = now + timedelta(days=day_offset)
            trip_date = trip_date_dt.date()
            self.stdout.write(f'Creating trips for day {day_offset + 1}/7...')
            
            for route_idx, (pickup, destination, price, duration_hours) in enumerate(routes):
                # Multiple trips per day
                departure_hours = [6, 8, 10, 12, 14, 16, 18, 20]
                
                for departure_hour in departure_hours:
                    departure_time = trip_date_dt.replace(hour=departure_hour, minute=0, second=0, microsecond=0)
                    arrival_time = departure_time + timedelta(hours=duration_hours)
                    
                    trip = Trip.objects.create(
                        operator=operator,
                        bus=buses[route_idx % len(buses)],
                        driver=drivers[route_idx % len(drivers)],
                        from_city=pickup,
                        to_city=destination,
                        journey_date=trip_date,
                        planned_polyline='',
                        planned_route_name=f'{pickup.city}-{destination.city} Route',
                        trip_type='scheduled',
                        planned_departure=departure_time,
                        price_per_km=50,
                        total_distance_km=price * 0.5,
                        status='scheduled'
                    )
                    
                    TripStop.objects.create(
                        trip=trip,
                        city=pickup,
                        sequence=0,
                        planned_arrival=departure_time,
                        planned_departure=departure_time,
                        distance_from_start_km=0,
                        price_from_start=0
                    )
                    
                    TripStop.objects.create(
                        trip=trip,
                        city=destination,
                        sequence=1,
                        planned_arrival=arrival_time,
                        planned_departure=arrival_time,
                        distance_from_start_km=price * 0.5,
                        price_from_start=price
                    )
                    
                    trip.initialize_seat_matrix(2)
                    
                    # Create seats in bulk
                    seats = []
                    for seat_num in range(1, 41):
                        seats.append(Seat(
                            trip=trip,
                            seat_number=f'{seat_num:02d}',
                            available_segments=['0-1']
                        ))
                    Seat.objects.bulk_create(seats)
                    
                    trip_count += 1

        self.stdout.write(
            self.style.SUCCESS(f'Successfully seeded {trip_count} trips')
        )
