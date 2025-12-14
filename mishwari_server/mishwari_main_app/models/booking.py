"""Booking-related models"""
from django.db import models
from django.contrib.auth.models import User


class Passenger(models.Model):
    GENDER_CHOICES = [
        ('male', 'male'),
        ('female', 'female')
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    age = models.IntegerField(null=True, blank=True)
    is_checked = models.BooleanField(default=False)
    gender = models.CharField(max_length=10, null=True, blank=True, choices=GENDER_CHOICES)

    def __str__(self):
        return self.name


class Booking(models.Model):
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

    trip = models.ForeignKey('Trip', on_delete=models.PROTECT, null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    from_stop = models.ForeignKey('TripStop', on_delete=models.PROTECT, related_name='bookings_from', null=True, blank=True)
    to_stop = models.ForeignKey('TripStop', on_delete=models.PROTECT, related_name='bookings_to', null=True, blank=True)
    passengers_data = models.JSONField(default=list)
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
        return [f"{i}-{i+1}" for i in range(self.from_stop.sequence, self.to_stop.sequence)]
    
    def calculate_fare(self):
        passenger_count = len(self.passengers_data)
        price_diff = self.to_stop.price_from_start - self.from_stop.price_from_start
        return price_diff * passenger_count
