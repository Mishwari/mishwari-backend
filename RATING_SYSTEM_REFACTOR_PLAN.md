# Rating System Refactor Plan - Mishwari Backend

## Overview
This document outlines the complete refactor plan to integrate a Read-Optimized Rating System with vehicle swap tracking into the Mishwari bus booking platform.

## Architecture Goals
1. **Read-Optimized**: Cache ratings on entities for fast search queries
2. **Write Integrity**: Link reviews to completed bookings only (prevent fake reviews)
3. **Swap Tracking**: Track actual vs planned resources (bus/driver changes)
4. **Health Score**: Automated operator scoring for platform governance

---

## Phase 1: Model Updates

### 1.1 New Model: TripReview

**File**: `mishwari_main_app/models.py`

```python
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
```

### 1.2 Update BusOperator Model

**Add to existing BusOperator**:

```python
# Rating cache (read-optimization)
avg_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0.00, db_index=True)
total_reviews = models.IntegerField(default=0)
```

### 1.3 Update Bus Model

**Add to existing Bus**:

```python
# Rating fields
avg_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0.00)
total_reviews = models.IntegerField(default=0)

# Amenity flags (replace JSON for faster filtering)
has_wifi = models.BooleanField(default=False)
has_ac = models.BooleanField(default=True)
has_usb_charging = models.BooleanField(default=False)
```

**Migration Note**: Create data migration to populate boolean flags from existing `amenities` JSON field.

### 1.4 Update Driver Model

**Add to existing Driver**:

```python
# Already has driver_rating field, just add:
total_reviews = models.IntegerField(default=0)
```

### 1.5 Update Trip Model - Actual vs Planned Resources

**Add to existing Trip**:

```python
# ACTUAL resources (filled when trip starts/completes - used for RATINGS)
actual_bus = models.ForeignKey(Bus, on_delete=models.SET_NULL, null=True, blank=True, related_name='actual_trips')
actual_driver = models.ForeignKey(Driver, on_delete=models.SET_NULL, null=True, blank=True, related_name='actual_trips')

def get_resources(self):
    """Returns actual resources if set, otherwise planned ones"""
    return {
        "bus": self.actual_bus or self.bus,
        "driver": self.actual_driver or self.driver
    }
```

**Note**: Keep existing `bus` and `driver` fields as "planned" resources. No breaking changes.

### 1.6 Update OperatorMetrics Model

**Add to existing OperatorMetrics**:

```python
# Performance metrics
on_time_performance = models.FloatField(default=100.0)
avg_response_time_minutes = models.IntegerField(default=60)

def recalculate_health_score(self):
    """Calculate health score: Rating×10 - Cancellation×2 - Strikes×15"""
    rating_score = float(self.operator.avg_rating) * 10
    cancellation_penalty = self.cancellation_rate * 2
    strike_penalty = self.strikes * 15
    
    score = rating_score - cancellation_penalty - strike_penalty
    self.health_score = max(0, min(100, int(score)))
    self.save()
```

---

## Phase 2: Serializer Updates

### 2.1 Create TripReviewSerializer

**File**: `mishwari_main_app/serializers.py`

```python
class TripReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = TripReview
        fields = ['id', 'booking', 'overall_rating', 'bus_condition_rating', 
                  'driver_rating', 'comment', 'created_at']
        read_only_fields = ['created_at']
    
    def validate_booking(self, value):
        """Ensure booking is completed and not already reviewed"""
        if value.status != 'completed':
            raise serializers.ValidationError("Can only review completed trips")
        if hasattr(value, 'review'):
            raise serializers.ValidationError("Booking already reviewed")
        return value
```

### 2.2 Update BusSerializer

**Modify fields list**:

```python
fields = ["id", "bus_number", "bus_type", "capacity", "amenities", 
          "is_verified", "verification_documents", 
          "avg_rating", "total_reviews", "has_wifi", "has_ac", "has_usb_charging"]
```

### 2.3 Update DriverSerializer

**Add total_reviews to fields**:

```python
fields = ['id', 'driver_name', 'mobile_number', 'email', 'national_id', 
          'driver_license', 'driver_rating', 'total_reviews', 'operator', 
          'buses', 'is_verified', 'verification_documents']
```

### 2.4 Update BusOperatorSerializer

```python
fields = ["id", "name", "avg_rating", "total_reviews"]
```

### 2.5 Update TripsSerializer

**Add methods to show actual resources**:

```python
bus = serializers.SerializerMethodField()
driver = serializers.SerializerMethodField()

def get_bus(self, obj):
    resources = obj.get_resources()
    return BusSerializer(resources['bus']).data if resources['bus'] else None

def get_driver(self, obj):
    resources = obj.get_resources()
    return DriverSerializer(resources['driver']).data if resources['driver'] else None
```

### 2.6 Update BookingSerializer2

**Add review field**:

```python
review = TripReviewSerializer(read_only=True)

# Add to fields list
fields = [...existing..., 'review']
```

---

## Phase 3: View Updates

### 3.1 Create TripReviewViewSet

**File**: `mishwari_main_app/views.py`

```python
class TripReviewViewSet(viewsets.ModelViewSet):
    """Trip review management"""
    serializer_class = TripReviewSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    
    def get_queryset(self):
        return TripReview.objects.filter(booking__user=self.request.user)
    
    def create(self, request):
        """Create review with resource snapshots"""
        booking_id = request.data.get('booking')
        
        try:
            booking = Booking.objects.get(id=booking_id, user=request.user)
        except Booking.DoesNotExist:
            return Response({'error': 'Booking not found'}, 
                          status=status.HTTP_404_NOT_FOUND)
        
        # Validate booking is completed
        if booking.status != 'completed':
            return Response({'error': 'Can only review completed trips'}, 
                          status=status.HTTP_400_BAD_REQUEST)
        
        # Check if already reviewed
        if hasattr(booking, 'review'):
            return Response({'error': 'Booking already reviewed'}, 
                          status=status.HTTP_400_BAD_REQUEST)
        
        # Get actual resources from trip
        trip = booking.trip
        resources = trip.get_resources()
        
        # Create review with snapshots
        review = TripReview.objects.create(
            booking=booking,
            bus_snapshot=resources['bus'],
            driver_snapshot=resources['driver'],
            operator_snapshot=trip.operator,
            overall_rating=request.data['overall_rating'],
            bus_condition_rating=request.data['bus_condition_rating'],
            driver_rating=request.data['driver_rating'],
            comment=request.data.get('comment', '')
        )
        
        serializer = self.get_serializer(review)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
```

### 3.2 Update TripSearchView

**Modify list method to include operator ratings**:

```python
# In results.append() section, update operator info:
'operator': {
    'id': trip.operator.id,
    'name': trip.operator.name,
    'avg_rating': float(trip.operator.avg_rating),
    'total_reviews': trip.operator.total_reviews
}
```

### 3.3 Update BookingViewSet

**Add action to complete bookings**:

```python
@action(detail=True, methods=['post'], url_path='complete')
def complete_booking(self, request, pk=None):
    """Mark booking as completed (driver/operator only)"""
    booking = self.get_object()
    
    # Permission check
    profile = request.user.profile
    if profile.role not in ['driver', 'operator_admin']:
        return Response({'error': 'Only drivers/operators can complete bookings'}, 
                       status=status.HTTP_403_FORBIDDEN)
    
    # Verify ownership
    if profile.role == 'driver':
        driver = Driver.objects.get(user=request.user)
        if booking.trip.driver != driver:
            return Response({'error': 'Not your trip'}, 
                          status=status.HTTP_403_FORBIDDEN)
    
    booking.status = 'completed'
    booking.save()
    
    return Response({'message': 'Booking completed successfully'})
```

### 3.4 Update OperatorTripViewSet

**Add action to set actual resources**:

```python
@action(detail=True, methods=['post'], url_path='set-actual-resources')
def set_actual_resources(self, request, pk=None):
    """Set actual bus/driver if different from planned"""
    trip = self.get_object()
    
    if request.user.profile.role != 'operator_admin':
        return Response({'error': 'Only operator_admin can swap resources'}, 
                       status=status.HTTP_403_FORBIDDEN)
    
    actual_bus_id = request.data.get('actual_bus')
    actual_driver_id = request.data.get('actual_driver')
    
    if actual_bus_id:
        trip.actual_bus = Bus.objects.get(id=actual_bus_id, operator=trip.operator)
    if actual_driver_id:
        trip.actual_driver = Driver.objects.get(id=actual_driver_id, operator=trip.operator)
    
    trip.save()
    
    return Response({'message': 'Actual resources updated'})
```

---

## Phase 4: Signals (Auto-Update Ratings)

### 4.1 Create signals.py

**File**: `mishwari_main_app/signals.py`

```python
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db.models import Avg
from .models import TripReview, Bus, Driver, BusOperator, Trip

@receiver(post_save, sender=TripReview)
def update_ratings_on_review(sender, instance, created, **kwargs):
    """Auto-update cached ratings when review is created"""
    if not created:
        return
    
    # Update Bus rating
    if instance.bus_snapshot:
        bus_reviews = TripReview.objects.filter(bus_snapshot=instance.bus_snapshot)
        avg = bus_reviews.aggregate(Avg('bus_condition_rating'))['bus_condition_rating__avg']
        instance.bus_snapshot.avg_rating = round(avg, 2) if avg else 0.00
        instance.bus_snapshot.total_reviews = bus_reviews.count()
        instance.bus_snapshot.save(update_fields=['avg_rating', 'total_reviews'])
    
    # Update Driver rating
    if instance.driver_snapshot:
        driver_reviews = TripReview.objects.filter(driver_snapshot=instance.driver_snapshot)
        avg = driver_reviews.aggregate(Avg('driver_rating'))['driver_rating__avg']
        instance.driver_snapshot.driver_rating = round(avg, 2) if avg else 0.00
        instance.driver_snapshot.total_reviews = driver_reviews.count()
        instance.driver_snapshot.save(update_fields=['driver_rating', 'total_reviews'])
    
    # Update Operator rating
    operator_reviews = TripReview.objects.filter(operator_snapshot=instance.operator_snapshot)
    avg = operator_reviews.aggregate(Avg('overall_rating'))['overall_rating__avg']
    instance.operator_snapshot.avg_rating = round(avg, 2) if avg else 0.00
    instance.operator_snapshot.total_reviews = operator_reviews.count()
    instance.operator_snapshot.save(update_fields=['avg_rating', 'total_reviews'])
    
    # Recalculate health score
    if hasattr(instance.operator_snapshot, 'metrics'):
        instance.operator_snapshot.metrics.recalculate_health_score()


@receiver(post_save, sender=Trip)
def update_health_score_on_trip_change(sender, instance, **kwargs):
    """Recalculate health score when trip is cancelled"""
    if instance.status == 'cancelled' and hasattr(instance.operator, 'metrics'):
        # Update cancellation rate
        total_trips = Trip.objects.filter(operator=instance.operator).count()
        cancelled_trips = Trip.objects.filter(operator=instance.operator, status='cancelled').count()
        
        if total_trips > 0:
            instance.operator.metrics.cancellation_rate = (cancelled_trips / total_trips) * 100
            instance.operator.metrics.save(update_fields=['cancellation_rate'])
        
        instance.operator.metrics.recalculate_health_score()
```

### 4.2 Register Signals

**File**: `mishwari_main_app/apps.py`

```python
from django.apps import AppConfig

class MishwariMainAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'mishwari_main_app'
    
    def ready(self):
        import mishwari_main_app.signals  # Register signals
```

---

## Phase 5: URL Configuration

### 5.1 Add Review Routes

**File**: `mishwari_main_app/urls.py` (or main urls.py)

```python
from .views import TripReviewViewSet

router.register(r'reviews', TripReviewViewSet, basename='review')
```

---

## Phase 6: Migration Strategy

### 6.1 Create Migrations

```bash
python manage.py makemigrations
```

### 6.2 Data Migration for Amenities

**Create custom migration**:

```python
# migrations/XXXX_populate_amenity_flags.py

from django.db import migrations

def populate_amenity_flags(apps, schema_editor):
    Bus = apps.get_model('mishwari_main_app', 'Bus')
    
    for bus in Bus.objects.all():
        amenities = bus.amenities or {}
        bus.has_wifi = amenities.get('wifi', False) or amenities.get('WiFi', False)
        bus.has_ac = amenities.get('ac', True) or amenities.get('AC', True)
        bus.has_usb_charging = amenities.get('usb', False) or amenities.get('USB', False)
        bus.save(update_fields=['has_wifi', 'has_ac', 'has_usb_charging'])

class Migration(migrations.Migration):
    dependencies = [
        ('mishwari_main_app', 'XXXX_add_rating_fields'),
    ]
    
    operations = [
        migrations.RunPython(populate_amenity_flags),
    ]
```

### 6.3 Run Migrations

```bash
python manage.py migrate
```

---

## Phase 7: Testing Checklist

### 7.1 Model Tests
- [ ] TripReview creation with snapshots
- [ ] Rating calculations (avg, total)
- [ ] Health score calculation
- [ ] Resource swap (actual vs planned)

### 7.2 API Tests
- [ ] Create review (completed booking only)
- [ ] Prevent duplicate reviews
- [ ] Prevent review on non-completed bookings
- [ ] Complete booking endpoint
- [ ] Set actual resources endpoint
- [ ] Search results include ratings

### 7.3 Signal Tests
- [ ] Ratings auto-update on review creation
- [ ] Health score recalculates on cancellation
- [ ] Cancellation rate updates

---

## Summary of Changes by File

| File | Changes | Type |
|------|---------|------|
| `models.py` | Add TripReview, update BusOperator/Bus/Driver/Trip/OperatorMetrics | Modify |
| `serializers.py` | Add TripReviewSerializer, update existing serializers | Modify |
| `views.py` | Add TripReviewViewSet, update TripSearchView, BookingViewSet | Modify |
| `operator_views.py` | Add set_actual_resources action | Modify |
| `signals.py` | Create new file with auto-update logic | New |
| `apps.py` | Register signals | Modify |
| `urls.py` | Add review routes | Modify |
| `migrations/` | Add rating fields, populate amenity flags | New |

---

## Key Design Decisions

1. **No Breaking Changes**: Keep existing `Trip.bus` and `Trip.driver` as planned resources
2. **Snapshot Pattern**: Store resource references in reviews (ratings stay with original performers)
3. **Read Optimization**: Cache ratings on entities for fast search queries
4. **Write Integrity**: Reviews linked to completed bookings only
5. **Automated Updates**: Signals handle rating recalculation
6. **Boolean Flags**: Convert amenities to flags for faster filtering
7. **Health Score Formula**: `(Rating×10) - (Cancellation×2) - (Strikes×15)`

---

## Implementation Order

1. ✅ Phase 1: Model updates
2. ✅ Phase 2: Serializer updates
3. ✅ Phase 3: View updates
4. ✅ Phase 4: Signals
5. ✅ Phase 5: URL configuration
6. ✅ Phase 6: Migrations
7. ✅ Phase 7: Testing

---

## Future Enhancements

- **Review Moderation**: Admin approval for reviews
- **Review Responses**: Allow operators to respond to reviews
- **Review Analytics**: Dashboard for operators
- **Trending Operators**: Sort by health_score in search
- **Review Photos**: Allow passengers to upload photos
- **Verified Reviews**: Badge for verified bookings

---

**Document Version**: 1.0  
**Last Updated**: 2024  
**Status**: Ready for Implementation
