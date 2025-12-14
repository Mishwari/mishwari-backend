"""Booking-related serializers"""
from rest_framework import serializers
from ..models import Booking, Passenger, Trip, TripStop
from .user_serializers import UserSerializer
from .trip_serializers import TripsSerializer, TripStopSerializer


class PassengerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Passenger
        fields = ['id', 'name', 'age', 'is_checked', 'gender']


class BookingTripSerializer(serializers.ModelSerializer):
    from_city = serializers.SerializerMethodField()
    to_city = serializers.SerializerMethodField()
    trip = TripsSerializer(read_only=True)

    class Meta:
        model = Booking
        fields = ['id', 'trip', 'from_city', 'to_city', 'total_fare', 'status', 'booking_time']
    
    def get_from_city(self, obj):
        from .trip_serializers import CitiesSerializer
        return CitiesSerializer(obj.from_stop.city).data if obj.from_stop else None
    
    def get_to_city(self, obj):
        from .trip_serializers import CitiesSerializer
        return CitiesSerializer(obj.to_stop.city).data if obj.to_stop else None


class BookingSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    trip = serializers.PrimaryKeyRelatedField(queryset=Trip.objects.all())
    from_stop = serializers.PrimaryKeyRelatedField(queryset=TripStop.objects.all())
    to_stop = serializers.PrimaryKeyRelatedField(queryset=TripStop.objects.all())
    passengers = serializers.ListField(child=serializers.DictField(), write_only=True)
    passengers_data = serializers.ListField(child=serializers.DictField(), read_only=True)
    review = serializers.SerializerMethodField()

    class Meta:
        model = Booking
        fields = ['id', 'user', 'status', 'total_fare', 'trip', 'from_stop', 'to_stop', 'passengers', 'passengers_data', 'contact_name', 'contact_phone', 'contact_email', 'is_paid', 'payment_method', 'booking_time', 'booking_source', 'created_by', 'review']
    
    def get_review(self, obj):
        from .review_serializers import TripReviewSerializer
        return TripReviewSerializer(obj.review).data if hasattr(obj, 'review') else None

    def validate(self, data):
        from ..utils.booking_utils import get_available_seats_for_journey
        
        trip = data.get('trip')
        from_stop = data.get('from_stop')
        to_stop = data.get('to_stop')
        passengers = self.initial_data.get('passengers', [])
        checked_passengers = [p for p in passengers if p.get('is_checked', False)]

        if trip and from_stop and to_stop:
            if trip.status not in ['published', 'active']:
                raise serializers.ValidationError(f"Cannot book trip with status '{trip.status}'. Only published or active trips can be booked.")
            
            available_seats = get_available_seats_for_journey(trip, from_stop, to_stop)
            
            if available_seats == 0:
                raise serializers.ValidationError(f"No seats available for this journey")
            if len(checked_passengers) > available_seats:
                raise serializers.ValidationError(f"Too many passengers. Only {available_seats} seats available.")
            
            expected_fare = (to_stop.price_from_start - from_stop.price_from_start) * len(checked_passengers)
            total_fare = data.get('total_fare')
            if total_fare != expected_fare:
                raise serializers.ValidationError(f"Invalid fare. Expected {expected_fare}, received {total_fare}.")
            
        return data

    def create(self, validated_data):
        from ..utils.booking_utils import create_booking_atomic
        
        initial_passengers_data = self.initial_data.get('passengers', [])
        user = self.context['request'].user
        
        trip_id = validated_data['trip'].id
        from_stop_id = validated_data['from_stop'].id
        to_stop_id = validated_data['to_stop'].id
        payment_method = validated_data.get('payment_method', 'cash')
        
        contact_name = validated_data.get('contact_name')
        contact_phone = validated_data.get('contact_phone')
        contact_email = validated_data.get('contact_email')
        
        booking = create_booking_atomic(
            trip_id=trip_id,
            from_stop_id=from_stop_id,
            to_stop_id=to_stop_id,
            user=user,
            passengers_data=initial_passengers_data,
            payment_method=payment_method,
            contact_name=contact_name,
            contact_phone=contact_phone,
            contact_email=contact_email
        )
        
        return booking

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['trip'] = TripsSerializer(instance.trip).data
        representation['from_stop'] = TripStopSerializer(instance.from_stop).data
        representation['to_stop'] = TripStopSerializer(instance.to_stop).data
        representation['passengers'] = instance.passengers_data
        return representation
