"""Review-related models"""
from django.db import models


class TripReview(models.Model):
    booking = models.OneToOneField('Booking', on_delete=models.CASCADE, related_name='review')
    bus_snapshot = models.ForeignKey('Bus', on_delete=models.SET_NULL, null=True)
    driver_snapshot = models.ForeignKey('Driver', on_delete=models.SET_NULL, null=True)
    operator_snapshot = models.ForeignKey('BusOperator', on_delete=models.CASCADE)
    overall_rating = models.PositiveSmallIntegerField()
    bus_condition_rating = models.PositiveSmallIntegerField()
    driver_rating = models.PositiveSmallIntegerField()
    comment = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        indexes = [models.Index(fields=['operator_snapshot', 'created_at'])]
    
    def __str__(self):
        return f"Review {self.id} for Booking {self.booking_id}"
