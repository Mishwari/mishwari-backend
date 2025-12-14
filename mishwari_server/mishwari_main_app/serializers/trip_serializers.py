"""Trip-related serializers"""
from rest_framework import serializers
from ..models import Trip, TripStop, CityList, Seat
from .operator_serializers import BusOperatorSerializer, BusSerializer, DriverSerializer


class CitiesSerializer(serializers.ModelSerializer):
    class Meta:
        model = CityList
        fields = ["id", "city"]


class TripStopSerializer(serializers.ModelSerializer):
    city = CitiesSerializer(read_only=True)

    class Meta:
        model = TripStop
        fields = ['id', 'city', 'sequence', 'planned_arrival', 'planned_departure', 'distance_from_start_km', 'price_from_start']


class TripsSerializer(serializers.ModelSerializer):
    driver = serializers.SerializerMethodField()
    bus = serializers.SerializerMethodField()
    operator = BusOperatorSerializer(read_only=True)
    from_city = CitiesSerializer(read_only=True)
    to_city = CitiesSerializer(read_only=True)
    stops = serializers.SerializerMethodField()
    
    departure_time = serializers.SerializerMethodField()
    arrival_time = serializers.SerializerMethodField()
    available_seats = serializers.SerializerMethodField()
    price = serializers.SerializerMethodField()
    can_publish = serializers.SerializerMethodField()

    class Meta:
        model = Trip
        fields = ['id', 'driver', 'planned_route_name', 'bus', 'operator', 'from_city', 'to_city', 'journey_date',
                  'departure_time', 'arrival_time', 'available_seats', 'price', 'status',
                  'trip_type', 'planned_departure', 'departure_window_start', 'departure_window_end', 'actual_departure',
                  'can_publish', 'stops', 'seat_matrix']
    
    def get_bus(self, obj):
        resources = obj.get_resources()
        return BusSerializer(resources['bus']).data if resources['bus'] else None
    
    def get_driver(self, obj):
        resources = obj.get_resources()
        return DriverSerializer(resources['driver']).data if resources['driver'] else None
    
    def get_departure_time(self, obj):
        first_stop = obj.stops.order_by('sequence').first()
        return first_stop.planned_departure if first_stop else None
    
    def get_arrival_time(self, obj):
        last_stop = obj.stops.order_by('sequence').last()
        return last_stop.planned_arrival if last_stop else None
    
    def get_available_seats(self, obj):
        return obj.get_min_available_seats()
    
    def get_price(self, obj):
        last_stop = obj.stops.order_by('sequence').last()
        return last_stop.price_from_start if last_stop else 0
    
    def get_can_publish(self, obj):
        return obj.can_publish()
    
    def get_stops(self, obj):
        stops = obj.stops.order_by('sequence').all()
        return [{
            'id': stop.id,
            'city': {'id': stop.city.id, 'name': stop.city.city},
            'sequence': stop.sequence,
            'distance_from_start_km': stop.distance_from_start_km,
            'price_from_start': stop.price_from_start,
            'planned_arrival': stop.planned_arrival,
            'planned_departure': stop.planned_departure
        } for stop in stops]


class SeatSerializer(serializers.ModelSerializer):
    trip_detail = serializers.CharField(source='trip.id', read_only=True)
    
    class Meta:
        model = Seat
        fields = ['id', 'seat_number', 'available_segments', 'trip_detail']
