"""User-related models"""
from django.db import models
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
        ('standalone_driver', 'Standalone Driver'),
        ('invited_driver', 'Invited Driver'),
        ('operator_admin', 'Operator Admin'),
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    mobile_number = models.CharField(max_length=15, unique=True, db_index=True)
    full_name = models.CharField(max_length=100, null=True, blank=True)
    address = models.CharField(max_length=150, null=True, blank=True)
    birth_date = models.CharField(max_length=20, blank=True, null=True)
    gender = models.CharField(max_length=10, null=True, blank=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='passenger')
    is_verified = models.BooleanField(default=True)
    security_pin = models.CharField(max_length=128, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.user.username
