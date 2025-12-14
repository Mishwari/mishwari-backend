"""Review-related serializers"""
from rest_framework import serializers
from ..models import TripReview


class TripReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = TripReview
        fields = ['id', 'booking', 'overall_rating', 'bus_condition_rating',
                  'driver_rating', 'comment', 'created_at']
        read_only_fields = ['created_at']
    
    def validate_booking(self, value):
        if value.status != 'completed':
            raise serializers.ValidationError("Can only review completed trips")
        if hasattr(value, 'review'):
            raise serializers.ValidationError("Booking already reviewed")
        return value
