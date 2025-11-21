import time
from django.shortcuts import render
from django.contrib.auth.models import User
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.conf import settings
from django.db import transaction
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist

from rest_framework import viewsets,status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny,IsAdminUser
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError

import stripe

import googlemaps
import polyline
from shapely.geometry import Point, LineString
from geopy.distance import geodesic
from datetime import timedelta

# for payment 
from .payment_gateways.stripe_payment_gateway import StripePaymentGateway
from .payment_gateways.wallet_payment_gateway import WalletPaymentGateway






from .serializers import (BookingSerializer2, UserSerializer,DriverSerializer,TripsSerializer,
                          TripStopSerializer,
                          CitiesSerializer,
                          BookingTripSerializer,
                          PassengerSerializer
                          )
from  .models import Driver, TripStop,Trip,CityList,Seat,Booking,Passenger,Bus

class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer


    def get_permissions(self):
        if self.request.method in ['GET']:
            return [IsAuthenticated()]
        return [IsAdminUser()]
    
class JwtUserView(viewsets.ModelViewSet):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def get_queryset(self):
        # This line gets the user ID from the JWT token and returns the corresponding user
        user = User.objects.filter(id=self.request.user.id).first()
        print('user: ',user)
        return User.objects.filter(id=self.request.user.id)


class DriverView(viewsets.ModelViewSet):
    queryset = Driver.objects.all()
    serializer_class = DriverSerializer

    
    def get_permissions(self):
        if self.request.method in ['GET']:
            return [IsAuthenticated()]
        return [IsAdminUser()]

class JwtDriverView(viewsets.ModelViewSet):
    serializer_class = DriverSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication] #recieved Token to user("user=user,non-admin")

    def get_queryset(self):
        # This line gets the user ID from the JWT token and returns the corresponding user
        return Driver.objects.filter(user=self.request.user.id)



from django.shortcuts import get_object_or_404
class TripStopView(viewsets.ModelViewSet):
    serializer_class = TripStopSerializer

    def get_queryset(self):
        trip_id = self.request.query_params.get('trip', None)
        
        # For non-admin users, only show stops for published trips
        if not self.request.user.is_staff:
            if trip_id:
                return TripStop.objects.filter(trip_id=trip_id, trip__status='published')
            return TripStop.objects.filter(trip__status='published')
        
        # Admins can see all stops
        if trip_id:
            return TripStop.objects.filter(trip_id=trip_id)
        return TripStop.objects.all()
        
    def retrieve(self, request, pk=None):
        qs = TripStop.objects.all()
        stop = get_object_or_404(qs, pk=pk)
        serializer = TripStopSerializer(stop, context={'request': request})
        return Response(serializer.data)
        
    def get_permissions(self):
        if self.request.method in ['GET']:
            return [AllowAny()]
        return [IsAdminUser()]
    


class TripSearchView(viewsets.ViewSet):
    """Search trips - supports partial journeys"""
    permission_classes = [AllowAny]
    
    def list(self, request):
        from_city = self.request.query_params.get('pickup') or self.request.query_params.get('from_city')
        to_city = self.request.query_params.get('destination') or self.request.query_params.get('to_city')
        date_str = self.request.query_params.get('date', None)

        if not all([from_city, to_city, date_str]):
            return Response({'error': 'from_city, to_city, and date required'}, status=status.HTTP_400_BAD_REQUEST)
        
        from datetime import datetime
        try:
            filter_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            from_city_obj = CityList.objects.get(city=from_city)
            to_city_obj = CityList.objects.get(city=to_city)
        except (ValueError, CityList.DoesNotExist):
            return Response({'error': 'Invalid date or city'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Find trips with BOTH cities as stops
        trips_with_from = TripStop.objects.filter(
            city=from_city_obj,
            trip__journey_date=filter_date,
            trip__status='published'
        ).values_list('trip_id', flat=True)
        
        trips_with_to = TripStop.objects.filter(
            city=to_city_obj,
            trip__journey_date=filter_date,
            trip__status='published'
        ).values_list('trip_id', flat=True)
        
        matching_trip_ids = set(trips_with_from) & set(trips_with_to)
        
        results = []
        for trip_id in matching_trip_ids:
            trip = Trip.objects.select_related('bus', 'driver').get(id=trip_id)
            
            from_stop = trip.stops.filter(city=from_city_obj).first()
            to_stop = trip.stops.filter(city=to_city_obj).first()
            
            if not from_stop or not to_stop or from_stop.sequence >= to_stop.sequence:
                continue
            
            # Calculate available seats for this segment
            segments = [f"{i}-{i+1}" for i in range(from_stop.sequence, to_stop.sequence)]
            available_seats = min([trip.seat_matrix.get(seg, 0) for seg in segments]) if segments else 0
            
            fare = to_stop.price_from_start - from_stop.price_from_start
            
            results.append({
                'id': trip.id,
                'trip_id': trip.id,
                'from_stop_id': from_stop.id,
                'to_stop_id': to_stop.id,
                'from_city': from_city,
                'to_city': to_city,
                'departure_time': from_stop.planned_departure,
                'arrival_time': to_stop.planned_arrival,
                'available_seats': available_seats,
                'fare': fare,
                'price': fare,
                'bus': {'id': trip.bus.id, 'bus_number': trip.bus.bus_number, 'bus_type': trip.bus.bus_type, 'capacity': trip.bus.capacity, 'amenities': trip.bus.amenities} if trip.bus else None,
                'driver': {'id': trip.driver.id, 'd_name': trip.driver.profile.full_name, 'driver_rating': float(trip.driver.driver_rating), 'operator': {'id': trip.driver.operator.id, 'name': trip.driver.operator.name}} if trip.driver else None,
                'trip_type': trip.trip_type,
                'status': trip.status,
                'planned_route_name': trip.planned_route_name
            })
        
        return Response(results, status=status.HTTP_200_OK)
    
    def retrieve(self, request, pk=None):
        trip = get_object_or_404(Trip.objects.filter(status='published'), pk=pk)
        serializer = TripsSerializer(trip)
        return Response(serializer.data)
    
    def get_permissions(self):
        return [AllowAny()]
    
     
class CitiesView(viewsets.ModelViewSet):
    queryset = CityList.objects.all()
    serializer_class = CitiesSerializer

    def get_permissions(self):
        if self.request.method in ['GET']:
            return [AllowAny()]
        return [IsAdminUser()]
    
    @action(detail=False, methods=['get'], url_path='departure-cities')
    def departure_cities(self, request):
        """Get cities that can be departure points (not last stops) with trip counts"""
        from datetime import datetime
        date_str = request.query_params.get('date')
        
        if not date_str:
            return Response({'error': 'date parameter required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            filter_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return Response({'error': 'Invalid date format'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Get trips for the date
        trips = Trip.objects.filter(journey_date=filter_date, status='published')
        
        # Find cities that are NOT the last stop in at least one trip
        valid_departure_cities = {}
        for trip in trips:
            stops = trip.stops.order_by('sequence')
            max_sequence = stops.last().sequence if stops.exists() else -1
            
            # All stops except the last one can be departure points
            for stop in stops.exclude(sequence=max_sequence):
                city_id = stop.city.id
                city_name = stop.city.city
                if city_id not in valid_departure_cities:
                    valid_departure_cities[city_id] = {'id': city_id, 'city': city_name, 'trip_count': 0}
                valid_departure_cities[city_id]['trip_count'] += 1
        
        result = sorted(valid_departure_cities.values(), key=lambda x: x['city'])
        return Response(result, status=status.HTTP_200_OK)
    
    @action(detail=False, methods=['get'], url_path='destination-cities')
    def destination_cities(self, request):
        """Get cities that have trips going to them from a specific city with trip counts"""
        from datetime import datetime
        from_city = request.query_params.get('from_city')
        date_str = request.query_params.get('date')
        
        if not all([from_city, date_str]):
            return Response({'error': 'from_city and date parameters required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            filter_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            from_city_obj = CityList.objects.get(city=from_city)
        except (ValueError, CityList.DoesNotExist):
            return Response({'error': 'Invalid date or city'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Get trips that have from_city as a stop
        trips_with_from_city = TripStop.objects.filter(
            city=from_city_obj,
            trip__journey_date=filter_date,
            trip__status='published'
        ).values_list('trip_id', flat=True)
        
        # Get from_city sequence for each trip
        from_city_sequences = {}
        for trip_id in trips_with_from_city:
            from_stop = TripStop.objects.filter(trip_id=trip_id, city=from_city_obj).first()
            if from_stop:
                from_city_sequences[trip_id] = from_stop.sequence
        
        # Get destination cities with higher sequence
        valid_destinations = set()
        for trip_id, from_seq in from_city_sequences.items():
            dest_stops = TripStop.objects.filter(trip_id=trip_id, sequence__gt=from_seq).exclude(city=from_city_obj)
            for stop in dest_stops:
                valid_destinations.add((stop.city.id, stop.city.city))
        
        # Count trips for each destination
        result = []
        for city_id, city_name in valid_destinations:
            trip_count = sum(1 for trip_id, from_seq in from_city_sequences.items()
                           if TripStop.objects.filter(trip_id=trip_id, city_id=city_id, sequence__gt=from_seq).exists())
            result.append({'id': city_id, 'city': city_name, 'trip_count': trip_count})
        
        result.sort(key=lambda x: x['city'])
        
        return Response(result, status=status.HTTP_200_OK)

    

    
class DriverTripView(viewsets.ModelViewSet):

    serializer_class = TripsSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def get_queryset(self):
        return Trip.objects.filter(driver__user=self.request.user.id)
    


class RouteViewSet(viewsets.ViewSet):
    api_key = ''
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]



    def list(self, request):
        startParams = request.query_params.get('start')
        endParams = request.query_params.get('end')

        user_id = request.user.id
        cache_key_routes = f'routes_{user_id}'
        cache_key_start_city = f'start_city_{user_id}'
        cache_key_end_city = f'end_city_{user_id}'
        

        try:
            start =CityList.objects.get(city=startParams)
            end =CityList.objects.get(city=endParams)

            cache.set(cache_key_start_city, {start.city:start.coordinates}, timeout=3600)
            cache.set(cache_key_end_city, {end.city:end.coordinates}, timeout=3600)
        except ObjectDoesNotExist:
            return Response({'message': 'you may have provided wrong start or end'}, status=status.HTTP_400_BAD_REQUEST)
        
        startCoords = start.coordinates
        endCoords = end.coordinates

            

        print(startCoords)

        if not startCoords and not endCoords:
            return Response({'message': 'provide start and end'}, status=status.HTTP_400_BAD_REQUEST)
        
        gmaps = googlemaps.Client(key=self.api_key)
        all_routes = gmaps.directions(startCoords, endCoords, mode='driving', alternatives=True, region='ye')

        cache.set(cache_key_routes, all_routes, timeout=3600)

        routes_info = [
            {'route' : idx , 'summary' : route['summary'], 'distance' : route['legs'][0]['distance']['text']}
            for idx, route in enumerate(all_routes)
            ]
     
        return Response(routes_info, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'])
    def waypoints(self, request, pk=None):

        user_id = request.user.id
        cache_key_routes = f'routes_{user_id}'
        cache_key_start_city = f'start_city_{user_id}'
        cache_key_end_city = f'end_city_{user_id}'
        cache_key_new_route = f'new_route_{user_id}'
        cache_key_close_cities = f'close_cities_{user_id}'
        cache_key_route_summary = f'route_summary_{user_id}'
        
        all_routes = cache.get(cache_key_routes)

        if not all_routes:
            return Response({'message': 'Route Data Expired or Not Found'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            
            selected_route = all_routes[int(pk)]
            route_polyline = polyline.decode(selected_route['overview_polyline']['points'])
            start_city = cache.get(cache_key_start_city)
            end_city = cache.get(cache_key_end_city)

  
            PROXIMITY_KM = 2.0
            cities = CityList.objects.exclude(city__in=[next(iter(start_city.items()))[0], next(iter(end_city.items()))[0]])
            matched_cities = {}
            
            for city in cities:
                best_waypoint = None
                best_distance = None
                
                for waypoint in city.waypoints:
                    coords = (waypoint['lat'], waypoint['lon'])
                    
                    if self.is_point_near_polyline(coords, route_polyline, PROXIMITY_KM):
                        nearest_point = self.find_nearest_point_on_route(coords, route_polyline)
                        if isinstance(nearest_point, Point):
                            distance_along_route = self.calculate_distance_along_route(
                                route_polyline,
                                (nearest_point.x, nearest_point.y)
                            )
                            
                            # Keep earliest waypoint on route for this city
                            if best_distance is None or distance_along_route < best_distance:
                                best_waypoint = waypoint
                                best_distance = distance_along_route
                
                # Add city only once with its best waypoint
                if best_waypoint is not None:
                    matched_cities[city.city] = (f"{best_waypoint['lat']}, {best_waypoint['lon']}", best_distance)
            
            close_cities = [(name, coords, dist) for name, (coords, dist) in matched_cities.items()]
            close_cities = sorted(close_cities, key=lambda x: x[2])
            print('close_cities: ',close_cities)
            close_points = [cp[0] for cp in close_cities]
            print('close_points: ',close_points)

            cache.set(cache_key_close_cities,close_cities, timeout=3600)

            gmaps = googlemaps.Client(key=self.api_key)
            waypoints_param = [wp[1] for wp in close_cities]  # Extract coordinates
            new_route = gmaps.directions(next(iter(start_city.items()))[1], next(iter(end_city.items()))[1], waypoints=waypoints_param, mode='driving', region='ye')


            cache.set(cache_key_new_route, new_route, timeout=3600) # to be used for creating later
            cache.set(cache_key_route_summary, selected_route['summary'], timeout=3600) 

            waypoint_distances = []
            cumulative_distance = 0
            cumulative_duration = 0
            for i, leg in enumerate(new_route[0]['legs']):
                distance = leg['distance']['value']  # Distance in meters
                duration = leg['duration']['value']  # Duration in seconds
                cumulative_distance += distance
                cumulative_duration += duration

                # Add data for each waypoint or the end city
                if i < len(close_cities):
                    waypoint_name = close_cities[i][0]  # Get city name
                else:
                    break
                    # waypoint_name = next(iter(end_city.items()))[0]  # Last leg to the end city

                waypoint_distances.append({
                    'waypoint_name': waypoint_name,
                    'cumulative_distance': f"{cumulative_distance/1000} km",  # Convert to km
                    'cumulative_duration': f"{cumulative_duration/60} minutes"  # Convert to minutes
                })

            return Response({
                            'start_city': f'{next(iter(start_city.items()))[0]}',
                            'end_city': f'{next(iter(end_city.items()))[0]}',
                            'waypoints':waypoint_distances,
                            },status=status.HTTP_200_OK)
        

        
        except KeyError:
            return Response({'message': 'provide selected route'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'message': f'Error while validating the key or key not found: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)
        
        
    # Identification of Close Cities
    def is_point_near_polyline(self, point, polyline, threshold=1.2):
        if isinstance(point, tuple) and len(point) == 2:
            shapely_point = Point(point)
            line = LineString(polyline)
            nearest_point_on_line = line.interpolate(line.project(shapely_point))
            nearest_point_tuple = (nearest_point_on_line.x, nearest_point_on_line.y)
            return geodesic(nearest_point_tuple, point).kilometers <= threshold
        else:
            raise ValueError("Invalid point format in is_point_near_polyline")
        
    # Ordering Waypoints Along the Route
    def find_nearest_point_on_route(self, point, polyline):
        if isinstance(point, tuple) and len(point) == 2:
            shapely_point = Point(point)
            line = LineString(polyline)
            return line.interpolate(line.project(shapely_point))
        else:
            raise ValueError("Invalid point format in find_nearest_point_on_route")
    
    # determines the distance along the route to the point from find_nearest_point_on_route
    def calculate_distance_along_route(self, polyline, point): #issue
        if len(polyline) < 2 :
            return 0
        if isinstance(point, tuple) and len(point) == 2:
            line = LineString(polyline)
            shapely_point = Point(point)
            projected_distance = line.project(shapely_point)
            if projected_distance < 1:
                return 0
            else:
                line_to_nearest_point = LineString(polyline[:int(projected_distance) + 1])
                return line_to_nearest_point.length
        else:
            raise ValueError("Invalid point format in calculate_distance_along_route")


class TripsViewSet(viewsets.ModelViewSet):
    queryset = Trip.objects.all()
    serializer_class = TripsSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def create(self, request,*args , **kwargs):
        serializer = self.get_serializer(data = request.data)
        serializer.is_valid(raise_exception = True)
        trip = serializer.save()

        user_id = request.user.id
        print("user_id: ", user_id)
        
        cache_key_start_city = f'start_city_{user_id}'
        cache_key_end_city = f'end_city_{user_id}'
        cache_key_new_route = f'new_route_{user_id}'
        cache_key_close_cities = f'close_cities_{user_id}'
        cache_key_route_summary = f'route_summary_{user_id}'

        start_city = cache.get(cache_key_start_city)
        end_city = cache.get(cache_key_end_city)
        close_cities = cache.get(cache_key_close_cities)
        new_route = cache.get(cache_key_new_route)
        route_summary = cache.get(cache_key_route_summary)

        

        if not all([start_city, end_city ,close_cities,new_route]):
            return Response({'message': 'Required route data not found in cache'}, status=status.HTTP_400_BAD_REQUEST)

        # if (not request.data.pickup == next(iter(start_city.items()))[0])  and (not request.data.destination == next(iter(end_city.items()))[0]):
        #     return Response({'message': 'Pickup and Destination Submitted are Different !!'}, status=status.HTTP_400_BAD_REQUEST)
        
        total_distance_main_trip = sum(leg['distance']['value'] for leg in new_route[0]['legs'])/1000
        arrival_time_main_trip = timedelta(seconds=sum(leg['duration']['value'] for leg in new_route[0]['legs'])) + trip.departure_time
        
        trip.path_road = route_summary
        trip.arrival_time = arrival_time_main_trip
        trip.distance = total_distance_main_trip
        trip.save()

        price_per_km = trip.price / total_distance_main_trip
        print('price_per_km',price_per_km)

        all_stops = [next(iter(start_city.items()))[0]] + [cp[0] for cp in close_cities] + [next(iter(end_city.items()))[0]] # ["A", "B", "C","D"]
            
        print('all_stops: ',all_stops)
        cumulative_distances = [0]  
        cumulative_durations = [0] 
        for leg in new_route[0]['legs']:
            cumulative_distances.append(cumulative_distances[-1] + leg['distance']['value'] / 1000)  
            cumulative_durations.append(cumulative_durations[-1] + leg['duration']['value'])  

        for i in range(len(all_stops) - 1): # 0,1,2,3
            for j in range(i + 1, len(all_stops)): # i = 0 : j= [1,2,3], i = 1 : j= [2,3] , i = 2 : j= [3]
                # if i == 0 and j == len(all_stops) - 1:  # Skip the main trip
                #     continue

                subtrip_distance = cumulative_distances[j] - cumulative_distances[i]
                subtrip_duration = cumulative_durations[j] - cumulative_durations[i]

                subtrip_price = round((subtrip_distance * price_per_km) / 100) * 100

                departure_time = trip.departure_time + timedelta(seconds=cumulative_durations[i])
                arrival_time = departure_time + timedelta(seconds=subtrip_duration)

                AllTrips.objects.create(
                    trip=trip,
                    pickup=all_stops[i],
                    destination=all_stops[j],
                    departure_time=departure_time,
                    arrival_time=arrival_time,
                    distance=subtrip_distance,
                    path_road=trip.path_road,
                    price=subtrip_price,
                    driver=trip.driver,
                    created_at=trip.created_at,
                    trip_status=trip.trip_status,
                    available_seats=trip.available_seats
                )

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
    def get_queryset(self):
        return Trip.objects.filter(driver__user=self.request.user.id)
    
# Booking Views
stripe_api_key = 'stripe_url_from_settings'
class BookingViewSet(viewsets.ModelViewSet):
    
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = BookingSerializer2

    def get_queryset(self): 
        print('Fetching bookings for user:', self.request.user, 'ID:', self.request.user.id)
        bookings = Booking.objects.filter(user=self.request.user.id)
        print(f'Found {bookings.count()} bookings')
        return bookings
    

   
    def create(self, request, *args, **kwargs):
        # time.sleep(5)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        payment_method = request.data.get('payment_method', 'stripe')
        gateway = None

        if payment_method == 'stripe':
            gateway = StripePaymentGateway()
        elif payment_method == 'wallet':
            gateway = WalletPaymentGateway()
        elif payment_method == 'cash':
            gateway = None
        else:
            raise ValidationError('Unsupported payment method')

        try:
            with transaction.atomic():
                booking_data = serializer.validated_data
                booking_data['user'] = request.user

                # Validation is already done in serializer
                trip_price = booking_data.get('total_fare', 0)

                booking = serializer.save(user=request.user)
                booking_details = {
                    'user': booking_data['user'],
                    'trip': booking_data['trip'],
                    'amount': booking_data.get('total_fare', 0),
                    'booking_id': booking.id
                }

                # if trip_price != booking.


                # Set booking source and creator
                booking.booking_source = 'platform'
                booking.created_by = request.user
                booking.save()
                
                if payment_method == 'stripe':
                    
                    payment_url = gateway.initiate_payment(booking_details)
                    headers = self.get_success_headers(serializer.data)
                    return Response({'payment_url': payment_url, 'booking_id': booking.id}, status=status.HTTP_202_ACCEPTED, headers=headers)
                elif payment_method == 'wallet':
                    gateway.initiate_payment(booking_details)
                    booking.status = 'active'
                    booking.is_paid = True
                    booking.payment_method = 'wallet'
                    booking.save()
                    return Response({'message': 'Payment successful using wallet', 'booking': serializer.data}, status=status.HTTP_200_OK)
                elif payment_method == 'cash':
                    booking.status = 'pending'
                    booking.save()
                    headers = self.get_success_headers(serializer.data)
                    return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
                else:
                    headers = self.get_success_headers(serializer.data)
                    return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
        except ValidationError as e:
            raise e
        except Exception as e:
            return Response({'error': 'An unexpected error occurred'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=True, methods=['post'], url_path='cancel')
    def cancel_booking(self, request, pk=None):
        from .booking_utils import cancel_booking_atomic, BookingAlreadyCancelledError
        
        booking = self.get_object()
        
        # Validate ownership
        if booking.user != request.user:
            return Response(
                {'error': 'You do not have permission to cancel this booking'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        try:
            cancel_booking_atomic(booking.id)
            return Response({'message': 'Booking cancelled successfully.'}, status=status.HTTP_200_OK)
        except BookingAlreadyCancelledError:
            return Response({'error': 'Booking is already cancelled.'}, status=status.HTTP_400_BAD_REQUEST)
    
@csrf_exempt
def stripe_webhook(request):
    payload = request.body
    print('received hook', payload)
    sig_header = request.META['HTTP_STRIPE_SIGNATURE']
    endpoint_secret = settings.STRIPE_WEBHOOK_SECRET

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, endpoint_secret
        )
    except ValueError as e:
        return JsonResponse({'error': str(e)}, status=400)
    except stripe.error.SignatureVerificationError as e:
        return JsonResponse({'error': str(e)}, status=400)

    if event['type'] == 'checkout.session.completed':
        print('session completed!!!')
        session = event['data']['object']
        handle_successful_payment(session)

    return JsonResponse({'status': 'success'}, status=200)

def handle_successful_payment(session):
    try:
        booking_id = session['metadata']['booking_id']
        print('booking_id:', booking_id)
        print('type of booking_id', type(booking_id))
        booking = Booking.objects.get(id=int(booking_id))
        booking.is_paid = True
        booking.status = 'active'
        booking.save()
    except Booking.DoesNotExist:
        pass
    




class BookingTripsViewSet(viewsets.ModelViewSet):
    queryset = Booking.objects.all()
    serializer_class = BookingTripSerializer


class PassengersViewSet(viewsets.ModelViewSet):
    serializer_class = PassengerSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def get_queryset(self):
        # This line gets the user ID from the JWT token and returns the corresponding user
        passengers = Passenger.objects.filter(user=self.request.user.id)
        print('passengers: ',passengers)
        return Passenger.objects.filter(user=self.request.user.id)
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
    
    def update(self, request, *args, **kwargs):
        """Override update to validate ownership"""
        passenger = self.get_object()
        if passenger.user != request.user:
            return Response(
                {'error': 'You do not have permission to update this passenger'},
                status=status.HTTP_403_FORBIDDEN
            )
        return super().update(request, *args, **kwargs)
    
    def partial_update(self, request, *args, **kwargs):
        """Override partial_update to validate ownership"""
        passenger = self.get_object()
        if passenger.user != request.user:
            return Response(
                {'error': 'You do not have permission to update this passenger'},
                status=status.HTTP_403_FORBIDDEN
            )
        return super().partial_update(request, *args, **kwargs)
    
    def destroy(self, request, *args, **kwargs):
        """Override destroy to validate ownership"""
        passenger = self.get_object()
        if passenger.user != request.user:
            return Response(
                {'error': 'You do not have permission to delete this passenger'},
                status=status.HTTP_403_FORBIDDEN
            )
        return super().destroy(request, *args, **kwargs)
    
    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        data = serializer.data
        
        # Auto-check account owner if exists
        user_profile = request.user.profile
        for passenger in data:
            if passenger.get('name') == user_profile.full_name:
                passenger['is_checked'] = True
        
        return Response(data)
    
    @action(detail=False, methods=['post'], url_path='bulk-update-checked')
    def bulk_update_checked(self, request):
        """Bulk update is_checked status for passengers"""
        passengers_data = request.data.get('passengers', [])
        
        for passenger_data in passengers_data:
            passenger_id = passenger_data.get('id')
            is_checked = passenger_data.get('is_checked', False)
            
            if passenger_id:
                try:
                    passenger = Passenger.objects.get(id=passenger_id, user=request.user)
                    passenger.is_checked = is_checked
                    passenger.save()
                except Passenger.DoesNotExist:
                    pass
        
        return Response({'message': 'Passengers updated successfully'}, status=status.HTTP_200_OK)