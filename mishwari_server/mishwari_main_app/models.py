from django.db import models
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models.signals import m2m_changed
from django.dispatch import receiver
from django.utils import timezone

from django.contrib.auth.models import User



class OTPAttempt(models.Model):
    mobile_number = models.CharField(max_length=15, unique=True, db_index=True)
    attempt_count = models.IntegerField(default=0)
    last_attempt = models.DateTimeField(auto_now=True)
    blocked_until = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        indexes = [models.Index(fields=['mobile_number', 'last_attempt'])]
    
    def __str__(self):
        return f"{self.mobile_number} - Attempts: {self.attempt_count}"


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
    is_verified = models.BooleanField(default=True) # To be false later
    
    # Security - only for driver PIN (operator_admin uses User.password)
    security_pin = models.CharField(max_length=128, null=True, blank=True, help_text="Hashed 6-digit PIN for drivers")
    
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
    is_verified = models.BooleanField(default=True) # To be false later
    
    # Rating cache (read-optimization)
    avg_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0.00, db_index=True)
    total_reviews = models.IntegerField(default=0) 

    # For platform operators only (null for external API operators)
    platform_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='owned_operator',
        help_text="Platform user who owns this operator (null for external operators)"
    )

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
    is_verified = models.BooleanField(default=True)  # To be false later
    verification_documents = models.JSONField(default=dict, blank=True)  # Store document URLs
    
    # Rating fields
    avg_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0.00)
    total_reviews = models.IntegerField(default=0)
    
    # Amenity flags
    has_wifi = models.BooleanField(default=False)
    has_ac = models.BooleanField(default=False)
    has_usb_charging = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.bus_number} - {self.bus_type}"

class Driver(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    profile= models.OneToOneField(Profile, on_delete=models.CASCADE)
    national_id = models.CharField(max_length=20, null=True, blank=True)
    driver_rating = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, default=0.00)
    driver_license = models.CharField(max_length=16, null=True, blank=True)
    buses = models.ManyToManyField(Bus, related_name='drivers', blank=True)
    operator = models.ForeignKey(BusOperator, on_delete=models.CASCADE )
    is_verified = models.BooleanField(default=True)  # To be false later
    verification_documents = models.JSONField(default=dict, blank=True)  # Store document URLs
    
    # Review count
    total_reviews = models.IntegerField(default=0)

    

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
    bus = models.ForeignKey(Bus, on_delete=models.SET_NULL, null=True, related_name='planned_trips')
    driver = models.ForeignKey(Driver, on_delete=models.SET_NULL, null=True, related_name='planned_trips')
    
    # ACTUAL resources (filled when trip starts/completes - used for RATINGS)
    actual_bus = models.ForeignKey(Bus, on_delete=models.SET_NULL, null=True, blank=True, related_name='actual_trips')
    actual_driver = models.ForeignKey(Driver, on_delete=models.SET_NULL, null=True, blank=True, related_name='actual_trips')
    
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
    
    def get_resources(self):
        """Returns actual resources if set, otherwise planned ones"""
        return {
            "bus": self.actual_bus or self.bus,
            "driver": self.actual_driver or self.driver
        }
    


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
    
    # Store passenger snapshots with seat assignments
    passengers_data = models.JSONField(default=list)
    # Format: [{"name": "...", "age": ..., "gender": "...", "seat_number": "..."}]
    
    # Contact details for booking confirmation
    contact_name = models.CharField(max_length=100, null=True, blank=True)
    contact_phone = models.CharField(max_length=15, null=True, blank=True)
    contact_email = models.EmailField(null=True, blank=True)
    
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
        passenger_count = len(self.passengers_data)
        price_diff = self.to_stop.price_from_start - self.from_stop.price_from_start
        return price_diff * passenger_count


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
    
    # Performance metrics
    on_time_performance = models.FloatField(default=100.0)
    avg_response_time_minutes = models.IntegerField(default=60)
    
    def __str__(self):
        return f"{self.operator.name} - Score: {self.health_score}"
    
    def recalculate_health_score(self):
        """Calculate health score: Rating×10 - Cancellation×2 - Strikes×15"""
        rating_score = float(self.operator.avg_rating) * 10
        cancellation_penalty = self.cancellation_rate * 2
        strike_penalty = self.strikes * 15
        
        score = rating_score - cancellation_penalty - strike_penalty
        self.health_score = max(0, min(100, int(score)))
        self.save()



class DriverInvitation(models.Model):
    """Driver invitation system for operator_admin"""
    operator = models.ForeignKey(BusOperator, on_delete=models.CASCADE, related_name='invitations')
    mobile_number = models.CharField(max_length=15)
    invite_code = models.CharField(max_length=8, unique=True, db_index=True)
    
    status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending'),
            ('accepted', 'Accepted'),
            ('expired', 'Expired'),
            ('cancelled', 'Cancelled')
        ],
        default='pending'
    )
    
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_invitations')
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    accepted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='accepted_invitations')
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['invite_code']),
            models.Index(fields=['mobile_number', 'status']),
        ]
    
    def __str__(self):
        return f"{self.operator.name} -> {self.mobile_number} ({self.status})"


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
            # Update profile role
            self.profile.role = 'operator_admin'
            self.profile.save()
            
            # Update operator details
            driver = Driver.objects.filter(user=self.user).first()
            if driver and driver.operator:
                operator = driver.operator
                operator.name = self.company_name
                operator.save()
                # Keep Driver record - they're still a driver, just also an admin now
            
            self.status = 'approved'
            self.reviewed_at = timezone.now()
            self.save()


class TripReview(models.Model):
    """Review system - write layer"""
    
    # Link to completed booking (prevents fake reviews)
    booking = models.OneToOneField('Booking', on_delete=models.CASCADE, related_name='review')
    
    # Snapshots at trip time (ratings stay with original performers)
    bus_snapshot = models.ForeignKey('Bus', on_delete=models.SET_NULL, null=True)
    driver_snapshot = models.ForeignKey('Driver', on_delete=models.SET_NULL, null=True)
    operator_snapshot = models.ForeignKey('BusOperator', on_delete=models.CASCADE)
    
    # Granular Ratings (1-5)
    overall_rating = models.PositiveSmallIntegerField()
    bus_condition_rating = models.PositiveSmallIntegerField(help_text="AC, Seats, Cleanliness")
    driver_rating = models.PositiveSmallIntegerField(help_text="Punctuality, Safety, Behavior")
    
    comment = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        indexes = [models.Index(fields=['operator_snapshot', 'created_at'])]
    
    def __str__(self):
        return f"Review {self.id} for Booking {self.booking_id}"
