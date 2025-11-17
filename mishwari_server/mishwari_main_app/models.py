from django.db import models
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models.signals import m2m_changed
from django.dispatch import receiver
from django.utils import timezone

from django.contrib.auth.models import User



class TemporaryMobileVerification(models.Model):
    mobile_number = models.CharField(max_length=15, unique=True)
    otp_code = models.CharField(max_length=6,blank=True, null=True)
    is_verified = models.BooleanField(default=False)
    otp_sent_at = models.DateTimeField(auto_now_add=True)
    attempts = models.IntegerField(default=0)

    def otp_is_valid(self):
        expiry_time = self.otp_sent_at + timezone.timedelta(minutes=10)
        return timezone.now() < expiry_time
    
    def __str__(self):
        return f"{self.mobile_number} - {self.otp_code}"


class Profile(models.Model):
    ROLE_CHOICES = [
        ('passenger', 'Passenger'),
        ('driver', 'Driver'),
        ('operator_admin', 'Operator Admin'),
        ('operator_staff', 'Operator Staff')
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    mobile_number = models.CharField(max_length=15, unique=True, db_index=True)
    full_name = models.CharField(max_length=100,null=True, blank=True)
    address = models.CharField(max_length=150,null=True, blank=True)
    birth_date = models.CharField(max_length=20, blank=True, null=True)
    gender = models.CharField(max_length=10, null=True, blank=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='passenger')
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.user.username




class CityList(models.Model):
    city = models.CharField(max_length=16, null=False, blank=False, unique=True)
    waypoints = models.JSONField(default=list)
    # Format: [{"lat": 24.7136, "lon": 46.6753, "name": "City Center"}, ...]

    def __str__(self):
        return f"{self.city} - {len(self.waypoints)} waypoint(s)"
    
    @property
    def latitude(self):
        return self.waypoints[0]['lat'] if self.waypoints else None
    
    @property
    def longitude(self):
        return self.waypoints[0]['lon'] if self.waypoints else None
    
    @property
    def coordinates(self):
        if self.waypoints:
            return f"{self.waypoints[0]['lat']}, {self.waypoints[0]['lon']}"
        return None
    

    # booking 

class BusOperator(models.Model):
    name = models.CharField(max_length=100)
    contact_info = models.CharField(max_length=100)
    uses_own_system = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=False)

    api_url = models.URLField(max_length=200, blank=True, null=True)
    api_key = models.CharField(max_length=200, blank=True, null=True)

    operational_regions = models.ManyToManyField('CityList')

    def __str__(self):
        return f"{self.name} {'external' if self.uses_own_system else 'local'}"
    
class Bus(models.Model):
    operator = models.ForeignKey(BusOperator, on_delete=models.CASCADE, related_name="buses")
    bus_number = models.CharField(max_length=10, null=False, blank=False, unique=True)
    bus_type = models.CharField(max_length=30, null=False, blank=False)
    capacity = models.IntegerField()
    amenities = models.JSONField(default=dict)  # Stores amenities as key-value pairs, such as AC, Wi-Fi, etc.
    is_verified = models.BooleanField(default=False)  # Bus-level verification
    verification_documents = models.JSONField(default=dict, blank=True)  # Store document URLs

    def __str__(self):
        return f"{self.bus_number} - {self.bus_type}"

class Driver(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    profile= models.OneToOneField(Profile, on_delete=models.CASCADE)
    national_id = models.CharField(max_length=20, null=True, blank=True)
    driver_rating = models.DecimalField(max_digits=5, decimal_places=2)
    driver_license = models.CharField(max_length=16, null=True, blank=True)
    buses = models.ManyToManyField(Bus, related_name='drivers')
    operator = models.ForeignKey(BusOperator, on_delete=models.CASCADE )
    is_verified = models.BooleanField(default=False)  # Driver-level verification
    verification_documents = models.JSONField(default=dict, blank=True)  # Store document URLs

    

    def __str__(self):
        return f"{self.profile.full_name}"
    


class Trip(models.Model):
    """Main trip with segment-based seat tracking"""
    
    TRIP_TYPE_CHOICES = [
        ('scheduled', 'Fixed Schedule'),
        ('flexible', 'Flexible Window'),
    ]
    
    # Basic info
    operator = models.ForeignKey(BusOperator, on_delete=models.PROTECT)
    bus = models.ForeignKey(Bus, on_delete=models.SET_NULL, null=True)
    driver = models.ForeignKey(Driver, on_delete=models.SET_NULL, null=True)
    
    from_city = models.ForeignKey(CityList, on_delete=models.PROTECT, related_name='trips_from')
    to_city = models.ForeignKey(CityList, on_delete=models.PROTECT, related_name='trips_to')
    journey_date = models.DateField(db_index=True)
    
    # Route data
    planned_polyline = models.TextField()
    planned_route_name = models.CharField(max_length=100, default="مسار غير معروف")
    
    # Trip type and timing
    trip_type = models.CharField(max_length=20, choices=TRIP_TYPE_CHOICES, default='scheduled')
    planned_departure = models.DateTimeField(null=True, blank=True)
    departure_window_start = models.DateTimeField(null=True, blank=True)
    departure_window_end = models.DateTimeField(null=True, blank=True)
    actual_departure = models.DateTimeField(null=True, blank=True)
    
    # Pricing
    price_per_km = models.DecimalField(max_digits=6, decimal_places=2, default=50.00)
    total_distance_km = models.FloatField(default=0.0)
    
    # Seat matrix (JSON - per segment)
    seat_matrix = models.JSONField(default=dict)
    # Format: {"0-1": 40, "1-2": 38, "2-3": 40}
    
    # Status
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('published', 'Published'),
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['from_city', 'to_city', 'journey_date']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"{self.from_city} → {self.to_city} ({self.journey_date})"
    
    def clean(self):
        """Validate trip before saving - Golden Rule enforcement"""
        if self.status == 'published':
            if not self.operator.is_verified:
                raise ValidationError("Operator must be verified to publish trips")
            if self.bus and not self.bus.is_verified:
                raise ValidationError("Bus must be verified to publish trips")
            if self.driver and not self.driver.is_verified:
                raise ValidationError("Driver must be verified to publish trips")
        
        # Validate trip type fields
        if self.trip_type == 'scheduled' and not self.planned_departure:
            raise ValidationError("Scheduled trips require planned_departure")
        if self.trip_type == 'flexible':
            if not (self.departure_window_start and self.departure_window_end):
                raise ValidationError("Flexible trips require departure window")
    
    def can_publish(self):
        """Check if trip can be published"""
        return (
            self.operator.is_verified and
            self.bus and self.bus.is_verified and
            self.driver and self.driver.is_verified
        )
    
    def initialize_seat_matrix(self, num_stops):
        """Initialize seat matrix for all segments"""
        capacity = self.bus.capacity if self.bus else 40
        self.seat_matrix = {f"{i}-{i+1}": capacity for i in range(num_stops - 1)}
        self.save()
    
    def get_min_available_seats(self):
        """Get minimum available seats across all segments"""
        return min(self.seat_matrix.values()) if self.seat_matrix else 0
    


class TripStop(models.Model):
    """Individual stops on a trip"""
    
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name='stops')
    city = models.ForeignKey(CityList, on_delete=models.PROTECT)
    sequence = models.IntegerField()
    
    # Times
    planned_arrival = models.DateTimeField()
    planned_departure = models.DateTimeField()
    actual_arrival = models.DateTimeField(null=True, blank=True)
    actual_departure = models.DateTimeField(null=True, blank=True)
    
    # Distance
    distance_from_start_km = models.FloatField(default=0.0)
    
    # Pricing (driver-editable, cumulative from start)
    price_from_start = models.IntegerField(default=0)
    
    # Activity (filled after trip)
    passengers_boarded = models.IntegerField(default=0)
    passengers_alighted = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['sequence']
        unique_together = ['trip', 'sequence']
        indexes = [
            models.Index(fields=['trip', 'sequence']),
        ]
    
    def __str__(self):
        return f"{self.trip} - Stop {self.sequence}: {self.city}"


class Seat(models.Model):
    """Seat with segment-based availability"""
    
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="seats")
    seat_number = models.CharField(max_length=3)
    
    # Segment-based availability
    available_segments = models.JSONField(default=list)
    # Format: ["0-1", "1-2", "2-3"] = available for these segments
    
    class Meta:
        unique_together = ['trip', 'seat_number']
    
    def __str__(self):
        return f"{self.trip} - Seat {self.seat_number}"
    
    def is_available_for_segments(self, segments):
        """Check if seat is available for all given segments"""
        return all(seg in self.available_segments for seg in segments)


# Passenger management
genderChoices = [(
        'male', 'male'),
        ('female', 'female') ]
       

class Passenger(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    email = models.EmailField(null=True, blank=True)
    phone = models.CharField(max_length=15, null=True, blank=True)
    age = models.IntegerField(null=True, blank=True)
    is_checked = models.BooleanField(default=False)
    gender = models.CharField(max_length=10, null=True, blank=True, choices=genderChoices)

    def __str__(self):
        return self.name


class Booking(models.Model):
    """Booking with segment-based journey tracking"""
    
    STATUS_CHOICES = [
        ('confirmed', 'Confirmed'),
        ('pending', 'Pending'),
        ('cancelled', 'Cancelled'),
        ('completed', 'Completed'),
    ]

    PAYMENT_CHOICES = [
        ('cash', 'Cash'),
        ('wallet', 'Wallet'),
        ('stripe', 'Stripe'),
    ]
    
    SOURCE_CHOICES = [
        ('platform', 'Platform (Web/App)'),
        ('physical', 'Physical (By Operator)'),
        ('external_api', 'External API Partner'),
    ]

    trip = models.ForeignKey(Trip, on_delete=models.PROTECT, null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    
    # Journey segment tracking (nullable for migration)
    from_stop = models.ForeignKey(TripStop, on_delete=models.PROTECT, related_name='bookings_from', null=True, blank=True)
    to_stop = models.ForeignKey(TripStop, on_delete=models.PROTECT, related_name='bookings_to', null=True, blank=True)
    
    passengers = models.ManyToManyField(Passenger, through='BookingPassenger')
    
    total_fare = models.IntegerField(default=0)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    payment_method = models.CharField(max_length=20, choices=PAYMENT_CHOICES, default='cash')
    is_paid = models.BooleanField(default=False)
    
    booking_source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='platform')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, related_name='created_bookings', null=True, blank=True)
    
    booking_time = models.DateTimeField(auto_now_add=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['trip', 'status']),
            models.Index(fields=['user', '-booking_time']),
        ]
    
    def __str__(self):
        return f"Booking by {self.user.username} - {self.from_stop.city} → {self.to_stop.city}"
    
    def get_crossed_segments(self):
        """Get list of segments this booking crosses"""
        return [f"{i}-{i+1}" for i in range(self.from_stop.sequence, self.to_stop.sequence)]
    
    def calculate_fare(self):
        """Calculate fare based on stop prices"""
        passenger_count = self.passengers.count()
        price_diff = self.to_stop.price_from_start - self.from_stop.price_from_start
        return price_diff * passenger_count
    
class BookingPassenger(models.Model):
    """Links passengers to bookings with seat assignments"""
    
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='passenger_details')
    passenger = models.ForeignKey(Passenger, on_delete=models.SET_NULL, null=True, blank=True)
    seat = models.ForeignKey(Seat, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Store passenger data to preserve it even if passenger is deleted
    name = models.CharField(max_length=100, default='Unknown')
    email = models.EmailField(null=True, blank=True)
    phone = models.CharField(max_length=15, null=True, blank=True)
    age = models.IntegerField(null=True, blank=True)
    gender = models.CharField(max_length=10, null=True, blank=True, choices=genderChoices)
    
    class Meta:
        unique_together = ['booking', 'seat']

    def __str__(self):
        return f"{self.name} - Seat {self.seat.seat_number if self.seat else 'N/A'}"
    
    def save(self, *args, **kwargs):
        # Copy passenger data if passenger exists and name is default/empty
        if self.passenger and (not self.name or self.name == 'Unknown'):
            self.name = self.passenger.name
            self.email = self.passenger.email
            self.phone = self.passenger.phone
            self.age = self.passenger.age
            self.gender = self.passenger.gender
        super().save(*args, **kwargs)
    


class OperatorMetrics(models.Model):
    """Track operator performance and trust metrics"""
    operator = models.OneToOneField(BusOperator, on_delete=models.CASCADE, related_name='metrics')
    health_score = models.IntegerField(default=100)
    cancellation_rate = models.FloatField(default=0.0)
    double_booking_count = models.IntegerField(default=0)
    strikes = models.IntegerField(default=0)
    is_suspended = models.BooleanField(default=False)
    trip_limit = models.IntegerField(default=2, help_text="Max concurrent trips for new operators")
    payout_hold_hours = models.IntegerField(default=24, help_text="Hours to hold payout after trip")
    
    def __str__(self):
        return f"{self.operator.name} - Score: {self.health_score}"



class UpgradeRequest(models.Model):
    """Track driver upgrade requests to operator_admin"""
    STATUS_CHOICES = [
        ('pending', 'Pending Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE)
    
    # Company info
    company_name = models.CharField(max_length=200)
    commercial_registration = models.CharField(max_length=100)
    tax_number = models.CharField(max_length=100, blank=True)
    
    # Documents
    documents = models.JSONField(default=dict)
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    rejection_reason = models.TextField(blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_upgrades')
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.profile.full_name} - {self.status}"
    
    def approve_upgrade(self):
        """Approve upgrade and migrate role"""
        with transaction.atomic():
            self.profile.role = 'operator_admin'
            self.profile.save()
            
            driver = Driver.objects.filter(user=self.user).first()
            if driver and driver.operator:
                driver.operator.name = self.company_name
                driver.operator.save()
            
            self.status = 'approved'
            self.reviewed_at = timezone.now()
            self.save()
