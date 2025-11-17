import random
from rest_framework import serializers
from django.contrib.auth.models import User
from .models import Driver,Trip,TripStop,CityList,Seat,Booking,Bus,BusOperator,Passenger,BookingPassenger, TemporaryMobileVerification,Profile


class MobileVerificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = TemporaryMobileVerification
        fields = ["mobile_number", "otp_code", "is_verified"]

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username","email","first_name","last_name"]
        # fields = "__all__"

# class JwtUserSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = User

class ProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    class Meta:
        model = Profile
        fields = ['id','user','mobile_number', 'full_name','birth_date', 'gender', 'address', 'role', 'is_verified']



class ProfileCompletionSerializer(serializers.ModelSerializer):
    username = serializers.CharField(write_only=True, required=True)
    email = serializers.EmailField(write_only=True, required=True)
    user = UserSerializer(read_only=True)
    # password = serializers.CharField(write_only=True, required=True)
    
    class Meta:
        model = Profile
        fields = ['user','username', 'full_name', 'birth_date', 'gender','address','email','role']
        extra_kwargs = {
            'full_name':{'required': True}, 
            'username':{'required': True},
        }

    def create(self, validated_data):
        username = validated_data.pop('username', None)
        email = validated_data.pop('email', None)
        # password = validated_data.pop('password')
        mobile_number = self.context.get('mobile_number', None)

        if not username : 
            raise serializers.ValidationError({'message': 'Username is required for profile creation'})
        
        user = User.objects.create_user(username=username, email=email)
        

        profile = Profile.objects.create(user=user,mobile_number=mobile_number, **validated_data)
        
        return profile
    

    def update(self, instance, validated_data): 
        print("validated data", validated_data)
        user = instance.user

        username = validated_data.get('username', user.username)
        email = validated_data.get('email', user.email)
        # password = validated_data.get('password', None)

        user.username = username
        user.email = email
        print("user", user.username)
        user.save()

        # profile
        instance.full_name = validated_data.get('full_name', instance.full_name)
        instance.birth_date = validated_data.get('birth_date', instance.birth_date)
        instance.gender = validated_data.get('gender', instance.gender)
        # instance.address = validated_data.get('address', instance.address)
        instance.save()
        
        return instance





class BusOperatorSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusOperator
        fields = ["id", "name"]
class DriverSerializer(serializers.ModelSerializer):
    operator = BusOperatorSerializer(read_only=True)
    driver_name = serializers.CharField(source='profile.full_name', read_only=True)
    
    class Meta:
        model = Driver 
        fields = ['id', 'driver_name', 'driver_rating', 'operator', 'is_verified', 'verification_documents']

class BusSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bus
        fields = ["id", "bus_number","bus_type", "capacity","amenities","is_verified","verification_documents"]

class CitiesSerializer(serializers.ModelSerializer):
    class Meta:
        model= CityList
        fields = ["id","city"]


class TripsSerializer(serializers.ModelSerializer):
    driver = DriverSerializer(read_only=True)
    bus = BusSerializer(read_only=True)
    from_city = CitiesSerializer(read_only=True)
    to_city = CitiesSerializer(read_only=True)
    stops = serializers.SerializerMethodField()
    
    # Add computed fields for backward compatibility
    departure_time = serializers.SerializerMethodField()
    arrival_time = serializers.SerializerMethodField()
    available_seats = serializers.SerializerMethodField()
    price = serializers.SerializerMethodField()
    can_publish = serializers.SerializerMethodField()

    class Meta:
        model = Trip
        fields = ['id','driver','planned_route_name','bus','from_city','to_city','journey_date',
                  'departure_time','arrival_time','available_seats','price','status',
                  'trip_type','planned_departure','departure_window_start','departure_window_end','actual_departure',
                  'can_publish','stops','seat_matrix']
    
    def get_departure_time(self, obj):
        """Ge`t departure time from first stop"""
        first_stop = obj.stops.order_by('sequence').first()
        return first_stop.planned_departure if first_stop else None
    
    def get_arrival_time(self, obj):
        """Get arrival time from last stop"""
        last_stop = obj.stops.order_by('sequence').last()
        return last_stop.planned_arrival if last_stop else None
    
    def get_available_seats(self, obj):
        """Get minimum available seats across all segments"""
        return obj.get_min_available_seats()
    
    def get_price(self, obj):
        """Get total price from first to last stop"""
        last_stop = obj.stops.order_by('sequence').last()
        return last_stop.price_from_start if last_stop else 0
    
    def get_can_publish(self, obj):
        """Check if trip can be published (Golden Rule)"""
        return obj.can_publish()
    
    def get_stops(self, obj):
        """Get all stops for this trip"""
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



class TripStopSerializer(serializers.ModelSerializer):
    city = CitiesSerializer(read_only=True)

    class Meta:
        model = TripStop
        fields = ['id','city','sequence','planned_arrival','planned_departure','distance_from_start_km','price_from_start']



# Removed CombinedTripSerializer - no longer needed with new architecture
    


# Booking Serializers

class SeatSerializer(serializers.ModelSerializer):       
    trip_detail = serializers.CharField(source='trip.id', read_only=True)                          
    class Meta:
        model = Seat
        fields = ['id', 'seat_number', 'available_segments','trip_detail']


class BookingTripSerializer(serializers.ModelSerializer):
    from_city = CitiesSerializer(read_only=True, source='from_stop.city')
    to_city = CitiesSerializer(read_only=True, source='to_stop.city')
    trip = TripsSerializer(read_only=True)

    class Meta: 
        model = Booking
        fields = ['id', 'trip', 'from_city', 'to_city', 'total_fare', 'status', 'booking_time']


class PassengerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Passenger
        fields = ['id', 'name', 'email', 'phone','age','is_checked','gender']

class BookingPassengerSerializer(serializers.ModelSerializer):
    """Serializer for BookingPassenger with denormalized fields"""
    seat_number = serializers.SerializerMethodField()
    
    class Meta:
        model = BookingPassenger
        fields = ['id', 'name', 'email', 'phone', 'age', 'gender', 'seat_number']
    
    def get_seat_number(self, obj):
        return obj.seat.seat_number if obj.seat else None

class BookingSerializer2(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    trip = serializers.PrimaryKeyRelatedField(queryset=Trip.objects.all())
    from_stop = serializers.PrimaryKeyRelatedField(queryset=TripStop.objects.all())
    to_stop = serializers.PrimaryKeyRelatedField(queryset=TripStop.objects.all())
    passengers = PassengerSerializer(many=True)
    passenger_details = BookingPassengerSerializer(many=True, read_only=True)

    class Meta:
        model = Booking
        fields = ['id', 'user', 'status', 'total_fare', 'trip', 'from_stop', 'to_stop', 'passengers', 'passenger_details', 'is_paid', 'payment_method', 'booking_time', 'booking_source', 'created_by']

    def validate(self, data):
        from .booking_utils import get_available_seats_for_journey
        
        trip = data.get('trip')
        from_stop = data.get('from_stop')
        to_stop = data.get('to_stop')
        passengers = self.initial_data.get('passengers', [])
        checked_passengers = [p for p in passengers if p.get('is_checked', False)]

        if trip and from_stop and to_stop:
            # Check segment-based availability
            available_seats = get_available_seats_for_journey(trip, from_stop, to_stop)
            
            if available_seats == 0:
                raise serializers.ValidationError(f"No seats available for this journey")
            if len(checked_passengers) > available_seats:
                raise serializers.ValidationError(f"Too many passengers. Only {available_seats} seats available.")
            
            # Validate fare based on checked passengers only
            expected_fare = (to_stop.price_from_start - from_stop.price_from_start) * len(checked_passengers)
            total_fare = data.get('total_fare')
            if total_fare != expected_fare:
                raise serializers.ValidationError(f"Invalid fare. Expected {expected_fare}, received {total_fare}.")
            
        return data

    def create(self, validated_data):
        from .booking_utils import create_booking_atomic
        
        initial_passengers_data = self.initial_data.get('passengers', [])
        user = self.context['request'].user
        
        trip_id = validated_data['trip'].id
        from_stop_id = validated_data['from_stop'].id
        to_stop_id = validated_data['to_stop'].id
        payment_method = validated_data.get('payment_method', 'cash')
        
        # Use atomic booking function
        booking = create_booking_atomic(
            trip_id=trip_id,
            from_stop_id=from_stop_id,
            to_stop_id=to_stop_id,
            user=user,
            passengers_data=initial_passengers_data,
            payment_method=payment_method
        )
        
        return booking


    # Removed assign_seats_and_passengers - now handled by create_booking_atomic

        
    
    # to_representation() is important to get all trip details when GET request and post booking using only trip.id
    def to_representation(self, instance): 
        representation = super().to_representation(instance)
        representation['trip'] = TripsSerializer(instance.trip).data
        representation['from_stop'] = TripStopSerializer(instance.from_stop).data
        representation['to_stop'] = TripStopSerializer(instance.to_stop).data
        # Use passenger_details (denormalized) instead of passengers (FK)
        representation['passengers'] = BookingPassengerSerializer(instance.passenger_details.all(), many=True).data
        return representation
    
    # LOOP validate passenger by id to ignore passenger if it already there
    # TODO: handle passenger updation
    #