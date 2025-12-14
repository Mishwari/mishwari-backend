"""Operator and fleet serializers"""
from rest_framework import serializers
from ..models import BusOperator, Bus, Driver


class BusOperatorSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusOperator
        fields = ["id", "name", "avg_rating", "total_reviews"]


class BusSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bus
        fields = ["id", "bus_number", "bus_type", "capacity", "is_verified", "verification_documents",
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
