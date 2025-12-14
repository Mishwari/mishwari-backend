"""Operator-related models"""
from django.db import models, transaction
from django.contrib.auth.models import User
from django.utils import timezone


class BusOperator(models.Model):
    name = models.CharField(max_length=100)
    contact_info = models.CharField(max_length=100)
    uses_own_system = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=True)
    avg_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0.00, db_index=True)
    total_reviews = models.IntegerField(default=0)
    platform_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='owned_operator')
    api_url = models.URLField(max_length=200, blank=True, null=True)
    api_key = models.CharField(max_length=200, blank=True, null=True)
    operational_regions = models.ManyToManyField('CityList')

    def __str__(self):
        return f"{self.name} {'external' if self.uses_own_system else 'local'}"


class OperatorMetrics(models.Model):
    operator = models.OneToOneField(BusOperator, on_delete=models.CASCADE, related_name='metrics')
    health_score = models.IntegerField(default=100)
    cancellation_rate = models.FloatField(default=0.0)
    double_booking_count = models.IntegerField(default=0)
    strikes = models.IntegerField(default=0)
    is_suspended = models.BooleanField(default=False)
    trip_limit = models.IntegerField(default=2)
    payout_hold_hours = models.IntegerField(default=24)
    on_time_performance = models.FloatField(default=100.0)
    avg_response_time_minutes = models.IntegerField(default=60)
    
    def __str__(self):
        return f"{self.operator.name} - Score: {self.health_score}"
    
    def recalculate_health_score(self):
        rating_score = float(self.operator.avg_rating) * 10
        cancellation_penalty = self.cancellation_rate * 2
        strike_penalty = self.strikes * 15
        score = rating_score - cancellation_penalty - strike_penalty
        self.health_score = max(0, min(100, int(score)))
        self.save()


class UpgradeRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    profile = models.ForeignKey('Profile', on_delete=models.CASCADE)
    company_name = models.CharField(max_length=200)
    commercial_registration = models.CharField(max_length=100)
    tax_number = models.CharField(max_length=100, blank=True)
    documents = models.JSONField(default=dict)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    rejection_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_upgrades')
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.profile.full_name} - {self.status}"
    
    def approve_upgrade(self):
        with transaction.atomic():
            if self.profile.role == 'standalone_driver':
                self.profile.role = 'operator_admin'
                self.profile.save()
            
            from .fleet import Driver
            driver = Driver.objects.filter(user=self.user).first()
            if driver and driver.operator:
                operator = driver.operator
                operator.name = self.company_name
                operator.save()
            
            self.status = 'approved'
            self.reviewed_at = timezone.now()
            self.save()
