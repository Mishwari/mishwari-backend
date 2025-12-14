"""Fleet-related models (Bus, Driver, Invitations)"""
from django.db import models
from django.contrib.auth.models import User


class Bus(models.Model):
    operator = models.ForeignKey('BusOperator', on_delete=models.CASCADE, related_name="buses")
    bus_number = models.CharField(max_length=10, null=False, blank=False, unique=True)
    bus_type = models.CharField(max_length=30, null=False, blank=False)
    capacity = models.IntegerField()
    is_verified = models.BooleanField(default=True)
    verification_documents = models.JSONField(default=dict, blank=True)
    avg_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0.00)
    total_reviews = models.IntegerField(default=0)
    has_wifi = models.BooleanField(default=False)
    has_ac = models.BooleanField(default=False)
    has_usb_charging = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.bus_number} - {self.bus_type}"


class Driver(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    profile = models.OneToOneField('Profile', on_delete=models.CASCADE)
    national_id = models.CharField(max_length=20, null=True, blank=True)
    driver_rating = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, default=0.00)
    driver_license = models.CharField(max_length=16, null=True, blank=True)
    buses = models.ManyToManyField(Bus, related_name='drivers', blank=True)
    operator = models.ForeignKey('BusOperator', on_delete=models.CASCADE)
    is_verified = models.BooleanField(default=True)
    verification_documents = models.JSONField(default=dict, blank=True)
    total_reviews = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.profile.full_name}"


class DriverInvitation(models.Model):
    operator = models.ForeignKey('BusOperator', on_delete=models.CASCADE, related_name='invitations')
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
