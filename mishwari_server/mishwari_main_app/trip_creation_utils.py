from django.db import transaction
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from .models import Trip, TripStop, Seat, CityList
from .route_utils import calculate_distance_along_route
import polyline as polyline_lib


@transaction.atomic
def create_trip_from_cached_route(operator, bus, driver, cached_data, selected_route, trip_data, selected_waypoint_ids, custom_prices=None):
    """Create trip using cached route data (NO new Google Maps API call)"""
    if custom_prices is None:
        custom_prices = {}
    
    # Get total distance and price
    main_leg = selected_route['legs'][0]
    total_distance_km = main_leg['distance']['value'] / 1000
    total_price = Decimal(str(trip_data.get('total_price', 0)))
    price_per_km = (total_price / Decimal(str(total_distance_km))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP) if total_distance_km > 0 else Decimal('0.00')
    
    # Get polyline for distance calculations
    polyline_points = polyline_lib.decode(selected_route['overview_polyline']['points'])
    
    # Create Trip
    trip = Trip.objects.create(
        operator=operator,
        bus=bus,
        driver=driver,
        from_city_id=cached_data['from_city']['id'],
        to_city_id=cached_data['to_city']['id'],
        journey_date=trip_data['journey_date'],
        planned_polyline=selected_route['overview_polyline']['points'],
        planned_route_name=selected_route.get('summary', f"{cached_data['from_city']['name']} - {cached_data['to_city']['name']}"),
        trip_type=trip_data.get('trip_type', 'scheduled'),
        planned_departure=trip_data.get('planned_departure') or None,
        departure_window_start=trip_data.get('departure_window_start') or None,
        departure_window_end=trip_data.get('departure_window_end') or None,
        price_per_km=price_per_km,
        total_distance_km=total_distance_km,
        status='draft'
    )
    
    # Build list of all stop IDs
    all_stop_ids = [cached_data['from_city']['id']] + selected_waypoint_ids + [cached_data['to_city']['id']]
    
    # Fetch all city objects
    all_cities_dict = CityList.objects.in_bulk(all_stop_ids)
    
    # Calculate distance for each stop
    stops_data = []
    for city_id in all_stop_ids:
        city = all_cities_dict.get(city_id)
        if not city:
            continue
        
        if city.id == cached_data['from_city']['id']:
            distance = 0
        elif city.id == cached_data['to_city']['id']:
            distance = total_distance_km
        else:
            point = (float(city.latitude), float(city.longitude))
            distance = calculate_distance_along_route(polyline_points, point)
        
        stops_data.append({'city': city, 'distance': distance})
    
    # Sort stops by distance
    sorted_stops = sorted(stops_data, key=lambda s: s['distance'])
    
    # Parse planned_departure or use window start for flexible trips
    departure_str = trip_data.get('planned_departure') or trip_data.get('departure_window_start')
    if isinstance(departure_str, str) and departure_str:
        try:
            departure_time = datetime.strptime(departure_str, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            try:
                departure_time = datetime.combine(
                    trip.journey_date,
                    datetime.strptime(departure_str, '%H:%M:%S').time()
                )
            except ValueError:
                departure_time = datetime.combine(trip.journey_date, datetime.min.time())
    else:
        departure_time = datetime.combine(trip.journey_date, datetime.min.time())
    
    # Create TripStops
    for i, stop_info in enumerate(sorted_stops):
        city = stop_info['city']
        distance = stop_info['distance']
        
        # Calculate price
        if str(city.id) in custom_prices:
            price = custom_prices[str(city.id)]
        elif city.id == cached_data['to_city']['id']:
            price = int(total_price)
        else:
            price = int(Decimal(str(distance)) * price_per_km)
        
        # Estimate duration (60 km/h average)
        duration_seconds = int((distance / 60) * 3600) if distance > 0 else 0
        
        TripStop.objects.create(
            trip=trip,
            city=city,
            sequence=i,
            distance_from_start_km=distance,
            price_from_start=price,
            planned_arrival=departure_time + timedelta(seconds=duration_seconds),
            planned_departure=departure_time + timedelta(seconds=duration_seconds + 300)
        )
    
    # Initialize seat matrix
    trip.initialize_seat_matrix(len(sorted_stops))
    
    # Create seats
    for seat_num in range(1, bus.capacity + 1):
        Seat.objects.create(
            trip=trip,
            seat_number=str(seat_num),
            available_segments=[f"{i}-{i+1}" for i in range(len(sorted_stops) - 1)]
        )
    
    return trip
