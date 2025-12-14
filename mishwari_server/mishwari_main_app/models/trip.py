"""Trip-related models"""
from django.db import models
from django.core.exceptions import ValidationError


class Trip(models.Model):
    TRIP_TYPE_CHOICES = [
        ('scheduled', 'Fixed Schedule'),
        ('flexible', 'Flexible Window'),
    ]
    
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('published', 'Published'),
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    
    operator = models.ForeignKey('BusOperator', on_delete=models.PROTECT)
    bus = models.ForeignKey('Bus', on_delete=models.SET_NULL, null=True, related_name='planned_trips')
    driver = models.ForeignKey('Driver', on_delete=models.SET_NULL, null=True, related_name='planned_trips')
    actual_bus = models.ForeignKey('Bus', on_delete=models.SET_NULL, null=True, blank=True, related_name='actual_trips')
    actual_driver = models.ForeignKey('Driver', on_delete=models.SET_NULL, null=True, blank=True, related_name='actual_trips')
    from_city = models.ForeignKey('CityList', on_delete=models.PROTECT, related_name='trips_from')
    to_city = models.ForeignKey('CityList', on_delete=models.PROTECT, related_name='trips_to')
    journey_date = models.DateField(db_index=True)
    planned_polyline = models.TextField()
    planned_route_name = models.CharField(max_length=100, default="مسار غير معروف")
    trip_type = models.CharField(max_length=20, choices=TRIP_TYPE_CHOICES, default='scheduled')
    planned_departure = models.DateTimeField(null=True, blank=True)
    departure_window_start = models.DateTimeField(null=True, blank=True)
    departure_window_end = models.DateTimeField(null=True, blank=True)
    actual_departure = models.DateTimeField(null=True, blank=True)
    price_per_km = models.DecimalField(max_digits=6, decimal_places=2, default=50.00)
    total_distance_km = models.FloatField(default=0.0)
    seat_matrix = models.JSONField(default=dict)
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
        if self.status == 'published':
            if not self.operator.is_verified:
                raise ValidationError("Operator must be verified to publish trips")
            if self.bus and not self.bus.is_verified:
                raise ValidationError("Bus must be verified to publish trips")
            if self.driver and not self.driver.is_verified:
                raise ValidationError("Driver must be verified to publish trips")
        
        if self.trip_type == 'scheduled' and not self.planned_departure:
            raise ValidationError("Scheduled trips require planned_departure")
        if self.trip_type == 'flexible':
            if not (self.departure_window_start and self.departure_window_end):
                raise ValidationError("Flexible trips require departure window")
    
    def can_publish(self):
        return (
            self.operator.is_verified and
            self.bus and self.bus.is_verified and
            self.driver and self.driver.is_verified
        )
    
    def initialize_seat_matrix(self, num_stops):
        capacity = self.bus.capacity if self.bus else 40
        self.seat_matrix = {f"{i}-{i+1}": capacity for i in range(num_stops - 1)}
        self.save()
    
    def get_min_available_seats(self):
        return min(self.seat_matrix.values()) if self.seat_matrix else 0
    
    def get_resources(self):
        return {
            "bus": self.actual_bus or self.bus,
            "driver": self.actual_driver or self.driver
        }


class TripStop(models.Model):
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name='stops')
    city = models.ForeignKey('CityList', on_delete=models.PROTECT)
    sequence = models.IntegerField()
    planned_arrival = models.DateTimeField()
    planned_departure = models.DateTimeField()
    actual_arrival = models.DateTimeField(null=True, blank=True)
    actual_departure = models.DateTimeField(null=True, blank=True)
    distance_from_start_km = models.FloatField(default=0.0)
    price_from_start = models.IntegerField(default=0)
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
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="seats")
    seat_number = models.CharField(max_length=3)
    available_segments = models.JSONField(default=list)
    
    class Meta:
        unique_together = ['trip', 'seat_number']
    
    def __str__(self):
        return f"{self.trip} - Seat {self.seat_number}"
    
    def is_available_for_segments(self, segments):
        return all(seg in self.available_segments for seg in segments)
