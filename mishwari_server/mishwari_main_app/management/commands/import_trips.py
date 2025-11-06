# command : python .\manage.py import_trips ./trips_seed.json
import json
import random
from datetime import datetime, timedelta
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from decimal import Decimal
from mishwari_main_app.models import (
    CityList, BusOperator, Bus, Driver, Trip, TripStop, Seat, User, Profile
)

class Command(BaseCommand):
    help = 'Load trips from JSON with dynamic dates and variations for 5 days'

    def add_arguments(self, parser):
        parser.add_argument('json_file', type=str, help='Path to the JSON file')

    def handle(self, *args, **kwargs):
        json_file_path = kwargs['json_file']
        try:
            with open(json_file_path, 'r', encoding='utf-8') as file:
                trip_templates = json.load(file)
                
                operator, _ = BusOperator.objects.get_or_create(
                    name='Mishwari Transport',
                    defaults={'contact_info': '+967-1-234567'}
                )
                
                today = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
                trip_count = 0
                
                for template in trip_templates:
                    try:
                        from_city = CityList.objects.get(city=template['from_city'])
                        to_city = CityList.objects.get(city=template['to_city'])
                    except CityList.DoesNotExist as e:
                        self.stdout.write(self.style.WARNING(f'City not found: {e}'))
                        continue
                    
                    for day in range(5):
                        trip_date = today + timedelta(days=day)
                        
                        for time_str in template['times']:
                            # Randomize per trip
                            price = int(template['base_price'] * random.uniform(0.95, 1.05))
                            seats = max(30, template['base_seats'] + random.randint(-5, 5))
                            # 20% chance of low rating (3.0-3.9), 80% high rating (4.0-5.0)
                            rating = round(random.uniform(3.0, 3.9) if random.random() < 0.2 else random.uniform(4.0, 5.0), 1)
                            
                            bus_num = f"YE-{random.randint(1000, 9999)}"
                            driver_num = random.randint(100, 999)
                            
                            bus, _ = Bus.objects.get_or_create(
                                bus_number=bus_num,
                                defaults={
                                    'operator': operator,
                                    'bus_type': random.choice(['جماعي', 'بلكة']),
                                    'capacity': seats,
                                    'amenities': {
                                        'ac': random.choice([True, False]),
                                        'wifi': random.choice([True, False]),
                                        'charger': random.choice([True, False])
                                    }
                                }
                            )
                            
                            user, _ = User.objects.get_or_create(
                                username=f'driver_{driver_num}',
                                defaults={'password': 'temp123'}
                            )
                            
                            profile, _ = Profile.objects.get_or_create(
                                user=user,
                                defaults={
                                    'mobile_number': f'+967-77-{random.randint(1000000, 9999999)}',
                                    'full_name': f'سائق {driver_num}',
                                    'role': 'driver'
                                }
                            )
                            
                            driver, created = Driver.objects.get_or_create(
                                user=user,
                                defaults={
                                    'profile': profile,
                                    'operator': operator,
                                    'driver_rating': Decimal(str(rating)),
                                    'national_id': f'{random.randint(10000000, 99999999)}'
                                }
                            )
                            
                            if created:
                                driver.buses.add(bus)
                            
                            hour, minute = map(int, time_str.split(':'))
                            departure = trip_date.replace(hour=hour, minute=minute)
                            arrival = departure + timedelta(hours=template['duration_hours'])
                            
                            trip = Trip.objects.create(
                                operator=operator,
                                bus=bus,
                                driver=driver,
                                from_city=from_city,
                                to_city=to_city,
                                journey_date=trip_date.date(),
                                planned_polyline='',
                                planned_route_name=template['route_name'],
                                price_per_km=Decimal('50.00'),
                                total_distance_km=template['distance_km'],
                                status='scheduled'
                            )
                            
                            TripStop.objects.create(
                                trip=trip,
                                city=from_city,
                                sequence=0,
                                planned_arrival=departure,
                                planned_departure=departure,
                                distance_from_start_km=0.0,
                                price_from_start=0
                            )
                            
                            TripStop.objects.create(
                                trip=trip,
                                city=to_city,
                                sequence=1,
                                planned_arrival=arrival,
                                planned_departure=arrival,
                                distance_from_start_km=template['distance_km'],
                                price_from_start=price
                            )
                            
                            trip.initialize_seat_matrix(2)
                            
                            for seat_num in range(1, seats + 1):
                                Seat.objects.create(
                                    trip=trip,
                                    seat_number=f'{seat_num:02d}',
                                    available_segments=['0-1']
                                )
                            
                            trip_count += 1
                
                self.stdout.write(self.style.SUCCESS(f'Successfully created {trip_count} trips'))
                
        except FileNotFoundError:
            raise CommandError(f'File "{json_file_path}" does not exist')
        except json.JSONDecodeError:
            raise CommandError(f'Error decoding JSON from "{json_file_path}"')
