import random
from rest_framework import serializers
from django.contrib.auth.models import User
from .models import Driver,Trip,TripStop,CityList,Seat,Booking,Bus,BusOperator,Passenger,Profile,TripReview

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
    is_standalone = serializers.SerializerMethodField()
    operator_name = serializers.SerializerMethodField()
    operator_contact = serializers.SerializerMethodField()
    operational_regions = serializers.SerializerMethodField()
    driver_license = serializers.SerializerMethodField()
    national_id = serializers.SerializerMethodField()
    pending_invitation_code = serializers.SerializerMethodField()
    
    class Meta:
        model = Profile
        fields = ['id','user','mobile_number', 'full_name','birth_date', 'gender', 'address', 'role', 'is_verified', 'is_standalone', 'operator_name', 'operator_contact', 'operational_regions', 'driver_license', 'national_id', 'pending_invitation_code']
    
    def get_is_standalone(self, obj):
        """Check if user is standalone (owns their operator)"""
        if obj.role in ['driver', 'operator_admin']:
            try:
                driver = Driver.objects.get(user=obj.user)
                return driver.operator.platform_user == obj.user
            except Driver.DoesNotExist:
                if obj.role == 'operator_admin':
                    try:
                        operator = BusOperator.objects.get(platform_user=obj.user)
                        return True
                    except BusOperator.DoesNotExist:
                        pass
        return False
    
    def get_operator_name(self, obj):
        """Get operator name if user is driver or operator_admin"""
        if obj.role in ['driver', 'operator_admin']:
            try:
                driver = Driver.objects.get(user=obj.user)
                return driver.operator.name
            except Driver.DoesNotExist:
                if obj.role == 'operator_admin':
                    try:
                        operator = BusOperator.objects.get(platform_user=obj.user)
                        return operator.name
                    except BusOperator.DoesNotExist:
                        pass
        return None
    
    def get_operator_contact(self, obj):
        """Get operator contact info"""
        if obj.role in ['driver', 'operator_admin']:
            try:
                driver = Driver.objects.get(user=obj.user)
                return driver.operator.contact_info
            except Driver.DoesNotExist:
                if obj.role == 'operator_admin':
                    try:
                        operator = BusOperator.objects.get(platform_user=obj.user)
                        return operator.contact_info
                    except BusOperator.DoesNotExist:
                        pass
        return None
    
    def get_driver_license(self, obj):
        """Get driver license if user is driver"""
        if obj.role in ['driver', 'operator_admin']:
            try:
                driver = Driver.objects.get(user=obj.user)
                return driver.driver_license
            except Driver.DoesNotExist:
                pass
        return None
    
    def get_national_id(self, obj):
        """Get national ID if user is driver"""
        if obj.role in ['driver', 'operator_admin']:
            try:
                driver = Driver.objects.get(user=obj.user)
                return driver.national_id
            except Driver.DoesNotExist:
                pass
        return None
    
    def get_operational_regions(self, obj):
        """Get operational regions"""
        if obj.role in ['driver', 'operator_admin']:
            try:
                driver = Driver.objects.get(user=obj.user)
                return list(driver.operator.operational_regions.values_list('city', flat=True))
            except Driver.DoesNotExist:
                if obj.role == 'operator_admin':
                    try:
                        operator = BusOperator.objects.get(platform_user=obj.user)
                        return list(operator.operational_regions.values_list('city', flat=True))
                    except BusOperator.DoesNotExist:
                        pass
        return []
    
    def get_pending_invitation_code(self, obj):
        """Get invitation code if invited driver has incomplete profile"""
        from .models import DriverInvitation
        from django.utils import timezone
        
        # Check if user is invited driver (not standalone) with incomplete profile
        if obj.role == 'driver' and not obj.full_name:
            try:
                driver = Driver.objects.get(user=obj.user)
                # Check if driver is invited (not standalone)
                if driver.operator.platform_user != obj.user:
                    # Find the invitation (can be pending or accepted)
                    invitation = DriverInvitation.objects.filter(
                        mobile_number=obj.mobile_number,
                        operator=driver.operator
                    ).order_by('-created_at').first()
                    if invitation:
                        return invitation.invite_code
            except Driver.DoesNotExist:
                pass
        return None



class ProfileCompletionSerializer(serializers.ModelSerializer):
    username = serializers.CharField(write_only=True, required=False)  # Optional for driver-web
    email = serializers.EmailField(write_only=True, required=True)
    user = UserSerializer(read_only=True)
    # password = serializers.CharField(write_only=True, required=True)
    
    class Meta:
        model = Profile
        fields = ['user','username', 'full_name', 'birth_date', 'gender','address','email','role']
        extra_kwargs = {
            'full_name':{'required': True},
        }

    def create(self, validated_data):
        username = validated_data.pop('username', None)
        email = validated_data.pop('email', None)
        # password = validated_data.pop('password')
        mobile_number = self.context.get('mobile_number', None)

        # Auto-use mobile number as username if not provided (for passenger-web)
        # Driver-web can still provide custom username
        if not username:
            username = mobile_number
        
        if not username:
            raise serializers.ValidationError({'message': 'Mobile number is required for profile creation'})
        
        user = User.objects.create_user(username=username, email=email)
        

        profile = Profile.objects.create(user=user,mobile_number=mobile_number, **validated_data)
        
        return profile
    

    def update(self, instance, validated_data): 
        user = instance.user
        username = validated_data.get('username', user.username)
        email = validated_data.get('email', user.email)
        user.username = username
        user.email = email
        user.save()

        # Update profile
        instance.full_name = validated_data.get('full_name', instance.full_name)
        instance.birth_date = validated_data.get('birth_date', instance.birth_date)
        instance.gender = validated_data.get('gender', instance.gender)
        instance.save()
        
        # Update operator if standalone
        operator_name = validated_data.get('operator_name')
        operator_contact = validated_data.get('operator_contact')
        operational_regions = validated_data.get('operational_regions')
        if operator_name or operator_contact or operational_regions is not None:
            try:
                driver = Driver.objects.get(user=user)
                if driver.operator.platform_user == user:
                    if operator_name:
                        driver.operator.name = operator_name
                    if operator_contact:
                        driver.operator.contact_info = operator_contact
                    if operational_regions is not None:
                        cities = CityList.objects.filter(city__in=operational_regions)
                        driver.operator.operational_regions.set(cities)
                    driver.operator.save()
            except Driver.DoesNotExist:
                if instance.role == 'operator_admin':
                    try:
                        operator = BusOperator.objects.get(platform_user=user)
                        if operator_name:
                            operator.name = operator_name
                        if operator_contact:
                            operator.contact_info = operator_contact
                        if operational_regions is not None:
                            cities = CityList.objects.filter(city__in=operational_regions)
                            operator.operational_regions.set(cities)
                        operator.save()
                    except BusOperator.DoesNotExist:
                        pass
        
        # Update driver details if exists
        driver_license = validated_data.get('driver_license')
        national_id = validated_data.get('national_id')
        if driver_license or national_id:
            try:
                driver = Driver.objects.get(user=user)
                if driver.operator.platform_user == user:
                    if driver_license:
                        driver.driver_license = driver_license
                    if national_id:
                        driver.national_id = national_id
                    driver.save()
            except Driver.DoesNotExist:
                pass
        
        return instance





class BusOperatorSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusOperator
        fields = ["id", "name", "avg_rating", "total_reviews"]

class BusSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bus
        fields = ["id", "bus_number","bus_type", "capacity","is_verified","verification_documents",
                  "avg_rating", "total_reviews", "has_wifi", "has_ac", "has_usb_charging"]

class DriverSerializer(serializers.ModelSerializer):
    operator = BusOperatorSerializer(read_only=True)
    driver_name = serializers.CharField(source='profile.full_name', read_only=True)
    mobile_number = serializers.CharField(source='profile.mobile_number', read_only=True)
    email = serializers.EmailField(source='user.email', read_only=True)
    buses = BusSerializer(many=True, read_only=True)
    
    class Meta:
        model = Driver 
        fields = ['id', 'driver_name', 'mobile_number', 'email', 'national_id', 'driver_license', 
                  'driver_rating', 'total_reviews', 'operator', 'buses', 'is_verified', 'verification_documents']

class CitiesSerializer(serializers.ModelSerializer):
    class Meta:
        model= CityList
        fields = ["id","city"]


class TripsSerializer(serializers.ModelSerializer):
    driver = serializers.SerializerMethodField()
    bus = serializers.SerializerMethodField()
    operator = BusOperatorSerializer(read_only=True)
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
        fields = ['id','driver','planned_route_name','bus','operator','from_city','to_city','journey_date',
                  'departure_time','arrival_time','available_seats','price','status',
                  'trip_type','planned_departure','departure_window_start','departure_window_end','actual_departure',
                  'can_publish','stops','seat_matrix']
    
    def get_bus(self, obj):
        """Return actual bus if set, otherwise planned bus"""
        resources = obj.get_resources()
        return BusSerializer(resources['bus']).data if resources['bus'] else None
    
    def get_driver(self, obj):
        """Return actual driver if set, otherwise planned driver"""
        resources = obj.get_resources()
        return DriverSerializer(resources['driver']).data if resources['driver'] else None
    
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
        fields = ['id', 'name', 'age', 'is_checked', 'gender']

class TripReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = TripReview
        fields = ['id', 'booking', 'overall_rating', 'bus_condition_rating', 
                  'driver_rating', 'comment', 'created_at']
        read_only_fields = ['created_at']
    
    def validate_booking(self, value):
        """Ensure booking is completed and not already reviewed"""
        if value.status != 'completed':
            raise serializers.ValidationError("Can only review completed trips")
        if hasattr(value, 'review'):
            raise serializers.ValidationError("Booking already reviewed")
        return value


class BookingSerializer2(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    trip = serializers.PrimaryKeyRelatedField(queryset=Trip.objects.all())
    from_stop = serializers.PrimaryKeyRelatedField(queryset=TripStop.objects.all())
    to_stop = serializers.PrimaryKeyRelatedField(queryset=TripStop.objects.all())
    passengers = serializers.ListField(child=serializers.DictField(), write_only=True)
    passengers_data = serializers.ListField(child=serializers.DictField(), read_only=True)
    review = TripReviewSerializer(read_only=True)

    class Meta:
        model = Booking
        fields = ['id', 'user', 'status', 'total_fare', 'trip', 'from_stop', 'to_stop', 'passengers', 'passengers_data', 'contact_name', 'contact_phone', 'contact_email', 'is_paid', 'payment_method', 'booking_time', 'booking_source', 'created_by', 'review']

    def validate(self, data):
        from .booking_utils import get_available_seats_for_journey
        
        trip = data.get('trip')
        from_stop = data.get('from_stop')
        to_stop = data.get('to_stop')
        passengers = self.initial_data.get('passengers', [])
        checked_passengers = [p for p in passengers if p.get('is_checked', False)]

        if trip and from_stop and to_stop:
            # Validate trip status
            if trip.status not in ['published', 'active']:
                raise serializers.ValidationError(f"Cannot book trip with status '{trip.status}'. Only published or active trips can be booked.")
            
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
        
        # Extract contact details
        contact_name = validated_data.get('contact_name')
        contact_phone = validated_data.get('contact_phone')
        contact_email = validated_data.get('contact_email')
        
        # Use atomic booking function
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


    # Removed assign_seats_and_passengers - now handled by create_booking_atomic

        
    
    # to_representation() is important to get all trip details when GET request and post booking using only trip.id
    def to_representation(self, instance): 
        representation = super().to_representation(instance)
        representation['trip'] = TripsSerializer(instance.trip).data
        representation['from_stop'] = TripStopSerializer(instance.from_stop).data
        representation['to_stop'] = TripStopSerializer(instance.to_stop).data
        representation['passengers'] = instance.passengers_data
        return representation
    
    # LOOP validate passenger by id to ignore passenger if it already there
    # TODO: handle passenger updation
    #