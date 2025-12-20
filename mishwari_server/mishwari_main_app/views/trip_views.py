"""Trip-related views"""
from datetime import datetime
from django.shortcuts import get_object_or_404
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAdminUser
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.decorators import action

from ..serializers import TripsSerializer, TripStopSerializer, CitiesSerializer
from ..models import Trip, TripStop, CityList


class TripStopView(viewsets.ModelViewSet):
    serializer_class = TripStopSerializer
    authentication_classes = []

    def get_queryset(self):
        trip_id = self.request.query_params.get('trip', None)
        
        if not self.request.user.is_staff:
            if trip_id:
                return TripStop.objects.filter(trip_id=trip_id, trip__status='published')
            return TripStop.objects.filter(trip__status='published')
        
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
    authentication_classes = []
    
    @action(detail=False, methods=['get'], url_path='recent')
    def recent_trips(self, request):
        """Get recently created published trips for homepage"""
        from django.utils import timezone
        
        today = timezone.now().date()
        trips = Trip.objects.filter(
            status='published',
            journey_date__gte=today
        ).select_related('from_city', 'to_city', 'operator', 'bus', 'driver').order_by('-created_at')[:8]
        
        results = []
        for trip in trips:
            first_stop = trip.stops.order_by('sequence').first()
            last_stop = trip.stops.order_by('-sequence').first()
            
            # Calculate price from first to last stop
            price = last_stop.price_from_start if last_stop else 0
            
            results.append({
                'id': trip.id,
                'from_city': {'name': trip.from_city.city},
                'to_city': {'name': trip.to_city.city},
                'journey_date': trip.journey_date,
                'departure_time': first_stop.planned_departure if first_stop else trip.planned_departure,
                'price': price,
                'available_seats': trip.get_min_available_seats(),
                'operator': {'name': trip.operator.name},
                'planned_route_name': trip.planned_route_name
            })
        
        return Response(results, status=status.HTTP_200_OK)
    
    def list(self, request):
        from_city = request.query_params.get('pickup') or request.query_params.get('from_city')
        to_city = request.query_params.get('destination') or request.query_params.get('to_city')
        date_str = request.query_params.get('date', None)

        if not all([from_city, to_city, date_str]):
            return Response({'error': 'from_city, to_city, and date required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            filter_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            from_city_obj = CityList.objects.get(city=from_city)
            to_city_obj = CityList.objects.get(city=to_city)
        except (ValueError, CityList.DoesNotExist):
            return Response({'error': 'Invalid date or city'}, status=status.HTTP_400_BAD_REQUEST)
        
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
                'bus': {'id': trip.bus.id, 'bus_number': trip.bus.bus_number, 'bus_type': trip.bus.bus_type, 'capacity': trip.bus.capacity, 'has_wifi': trip.bus.has_wifi, 'has_ac': trip.bus.has_ac, 'has_usb_charging': trip.bus.has_usb_charging} if trip.bus else None,
                'driver': {'id': trip.driver.id, 'd_name': trip.driver.profile.full_name, 'driver_rating': float(trip.driver.driver_rating), 'operator': {'id': trip.driver.operator.id, 'name': trip.driver.operator.name}} if trip.driver else None,
                'operator': {'id': trip.operator.id, 'name': trip.operator.name, 'avg_rating': float(trip.operator.avg_rating), 'total_reviews': trip.operator.total_reviews},
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
    
    @action(detail=False, methods=['get'], url_path='departure-cities', permission_classes=[AllowAny], authentication_classes=[])
    def departure_cities(self, request):
        date_str = request.query_params.get('date')
        if not date_str:
            return Response({'error': 'date parameter required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            filter_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return Response({'error': 'Invalid date format'}, status=status.HTTP_400_BAD_REQUEST)
        
        trips = Trip.objects.filter(journey_date=filter_date, status='published')
        valid_departure_cities = {}
        
        for trip in trips:
            stops = trip.stops.order_by('sequence')
            max_sequence = stops.last().sequence if stops.exists() else -1
            
            for stop in stops.exclude(sequence=max_sequence):
                city_id = stop.city.id
                city_name = stop.city.city
                if city_id not in valid_departure_cities:
                    valid_departure_cities[city_id] = {'id': city_id, 'city': city_name, 'trip_count': 0}
                valid_departure_cities[city_id]['trip_count'] += 1
        
        result = sorted(valid_departure_cities.values(), key=lambda x: x['city'])
        return Response(result, status=status.HTTP_200_OK)
    
    @action(detail=False, methods=['get'], url_path='destination-cities', permission_classes=[AllowAny], authentication_classes=[])
    def destination_cities(self, request):
        from_city = request.query_params.get('from_city')
        date_str = request.query_params.get('date')
        
        if not all([from_city, date_str]):
            return Response({'error': 'from_city and date parameters required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            filter_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            from_city_obj = CityList.objects.get(city=from_city)
        except (ValueError, CityList.DoesNotExist):
            return Response({'error': 'Invalid date or city'}, status=status.HTTP_400_BAD_REQUEST)
        
        trips_with_from_city = TripStop.objects.filter(
            city=from_city_obj,
            trip__journey_date=filter_date,
            trip__status='published'
        ).values_list('trip_id', flat=True)
        
        from_city_sequences = {}
        for trip_id in trips_with_from_city:
            from_stop = TripStop.objects.filter(trip_id=trip_id, city=from_city_obj).first()
            if from_stop:
                from_city_sequences[trip_id] = from_stop.sequence
        
        valid_destinations = set()
        for trip_id, from_seq in from_city_sequences.items():
            dest_stops = TripStop.objects.filter(trip_id=trip_id, sequence__gt=from_seq).exclude(city=from_city_obj)
            for stop in dest_stops:
                valid_destinations.add((stop.city.id, stop.city.city))
        
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
