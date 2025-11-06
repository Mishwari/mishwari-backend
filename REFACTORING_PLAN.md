# Mishwari Backend Refactoring Plan
## Trip Stops & Routes System Redesign

**Version:** 3.0  
**Date:** 2024  
**Status:** Planning Phase - DO NOT IMPLEMENT YET

---

## Recent Implementation Summary

### ✅ Completed Features (Phases 1-4)
- **Multi-Role System**: Passengers, Drivers, Operators with role-based permissions
- **Flexible Trip Scheduling**: Scheduled trips (fixed departure) + Flexible trips (departure window)
- **Operator SaaS Platform**: Fleet management, trip creation, physical booking recording
- **Trust & Safety**: Operator verification workflow, metrics tracking, health score system
- **Booking Source Tracking**: Platform bookings (web/app), physical bookings (by operator)

### New API Endpoints
- `POST /api/operator/fleet/` - Add bus to fleet
- `GET /api/operator/fleet/` - List operator's buses
- `POST /api/operator/trips/` - Create trip (scheduled or flexible)
- `POST /api/operator/trips/{id}/depart_now/` - Trigger departure for flexible trips
- `POST /api/operator/bookings/` - Record physical booking

### Database Changes
- **Profile**: Added `role` (passenger/driver/operator_admin/operator_staff), `is_verified`
- **Trip**: Added `trip_type` (scheduled/flexible), `planned_departure`, `departure_window_start`, `departure_window_end`, `actual_departure`
- **Booking**: Added `booking_source` (platform/physical/external_api), `created_by`
- **New Model**: `OperatorMetrics` for trust & safety tracking

### Deployment Steps
1. Run migrations: `python manage.py makemigrations && python manage.py migrate`
2. Update existing data: `python manage.py shell < update_existing_data.py`
3. Verify operators via Django Admin
4. Update frontend types for new fields

---

## Executive Summary

### Current Problems
1. ❌ **Broken Seat Availability**: All sub-trips share same `available_seats` value
2. ❌ **Database Bloat**: Creates n² sub-trips (6 stops = 15 records)
3. ❌ **No Route Learning**: Relies only on Google Maps, doesn't learn from history
4. ❌ **Scalability Issues**: Performance degrades with more stops

### Proposed Solution
**Practical 2-Phase System**:
- **Phase 1**: Fix core issues + Google Maps (3 weeks)
- **Phase 2**: Route learning with GPS + driver feedback (8 weeks)

### Expected Outcomes
- ✅ Correct seat availability tracking
- ✅ 52% reduction in database records
- ✅ Self-learning route database
- ✅ Works in any geography
- ✅ No ML complexity

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     PHASE 1: CORE FIX                       │
│                   (Week 1-3)                                │
├─────────────────────────────────────────────────────────────┤
│  Fix seat bug → Segment-based tracking → Dynamic search    │
│  → Use Google Maps → Production ready                      │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                  PHASE 2: ROUTE LEARNING                    │
│                   (Week 4-11)                               │
├─────────────────────────────────────────────────────────────┤
│  GPS tracking → Store actual routes → Build template DB    │
│  → Driver feedback → Frequency-based suggestions           │
└─────────────────────────────────────────────────────────────┘
```

**Key Principle**: "Trust but Verify"
- Start with Google Maps (fast launch)
- Learn from real trips (GPS + feedback)
- Build centralized route database
- Suggest based on frequency (no ML needed)

---

## Database Schema

### Core Models (Phase 1)

#### 1. Trip
```python
class Trip(models.Model):
    """Actual trip on specific date"""
    
    # Link to learned route (null initially)
    route_template = ForeignKey('RouteTemplate', null=True, blank=True)
    
    # Basic info
    operator = ForeignKey(BusOperator)
    bus = ForeignKey(Bus, null=True)
    driver = ForeignKey(Driver, null=True)
    
    from_city = ForeignKey(City, related_name='trips_from')
    to_city = ForeignKey(City, related_name='trips_to')
    journey_date = DateField(db_index=True)
    
    # Route data
    planned_polyline = TextField()  # From Google or template
    planned_route_name = CharField(max_length=100)  # "Highway Route"
    actual_polyline = TextField(null=True)  # GPS data after trip
    
    # Pricing
    base_price = IntegerField()
    total_distance_km = FloatField()
    
    # Seat matrix (JSON - per segment)
    seat_matrix = JSONField(default=dict)
    # {"0-1": 40, "1-2": 38, "2-3": 40}
    
    # Status
    status = CharField(max_length=20, default='scheduled')
    
    created_at = DateTimeField(auto_now_add=True)
    completed_at = DateTimeField(null=True)
```

#### 2. TripStop
```python
class TripStop(models.Model):
    """Stops on a trip"""
    
    trip = ForeignKey(Trip, related_name='stops')
    city = ForeignKey(City)
    sequence = IntegerField()
    
    # Times
    planned_arrival = DateTimeField()
    planned_departure = DateTimeField()
    actual_arrival = DateTimeField(null=True)
    actual_departure = DateTimeField(null=True)
    
    # Distance
    distance_from_start_km = FloatField()
    
    # Pricing (driver-editable)
    price_from_start = IntegerField()  # Cumulative price from origin
    
    # Activity (filled after trip)
    passengers_boarded = IntegerField(default=0)
    passengers_alighted = IntegerField(default=0)
    
    class Meta:
        ordering = ['sequence']
        unique_together = ['trip', 'sequence']
```

#### 3. Booking (Refactored)
```python
class Booking(models.Model):
    trip = ForeignKey(Trip, on_delete=PROTECT)
    user = ForeignKey(User)
    
    # Journey between stops
    from_stop = ForeignKey(TripStop, related_name='bookings_from')
    to_stop = ForeignKey(TripStop, related_name='bookings_to')
    
    passenger_count = IntegerField()
    total_fare = IntegerField()
    
    # Status
    status = CharField(max_length=20, default='confirmed')
    payment_method = CharField(max_length=20)
    is_paid = BooleanField(default=False)
    
    booking_time = DateTimeField(auto_now_add=True)
```

### Learning Models (Phase 2)

#### 4. RouteTemplate
```python
class RouteTemplate(models.Model):
    """Learned routes (centralized knowledge)"""
    
    from_city = ForeignKey(City, related_name='routes_from')
    to_city = ForeignKey(City, related_name='routes_to')
    
    name = CharField(max_length=100)  # "Highway Route"
    polyline = TextField()  # Encoded path
    
    # Metrics
    distance_km = FloatField()
    avg_duration_minutes = IntegerField()
    
    # Statistics (simple counters)
    times_used = IntegerField(default=0)
    times_completed = IntegerField(default=0)
    success_rate = FloatField(default=0.0)  # completed / used
    
    # Source
    source = CharField(max_length=20, choices=[
        ('google', 'Google Maps'),
        ('gps', 'GPS Learned'),
        ('manual', 'Driver Created'),
    ])
    
    # Verification
    is_verified = BooleanField(default=False)  # After 3+ trips
    is_active = BooleanField(default=True)
    
    created_at = DateTimeField(auto_now_add=True)
    last_used = DateTimeField(null=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['from_city', 'to_city', '-times_used']),
        ]
```

#### 5. RouteTemplateStop
```python
class RouteTemplateStop(models.Model):
    """Stops on route template"""
    
    route_template = ForeignKey(RouteTemplate, related_name='stops')
    city = ForeignKey(City)
    sequence = IntegerField()
    
    # Position
    distance_from_start_km = FloatField()
    duration_from_start_minutes = IntegerField()
    
    # Confidence (0-1)
    confidence = FloatField(default=1.0)
    
    # Statistics
    times_used = IntegerField(default=0)
    times_skipped = IntegerField(default=0)
    
    class Meta:
        ordering = ['sequence']
        unique_together = ['route_template', 'sequence']
```

#### 6. RouteCorrection
```python
class RouteCorrection(models.Model):
    """Track route improvements"""
    
    route_template = ForeignKey(RouteTemplate)
    trip = ForeignKey(Trip)
    
    correction_type = CharField(max_length=20, choices=[
        ('stop_added', 'Stop Added'),
        ('stop_removed', 'Stop Removed'),
        ('stop_replaced', 'Stop Replaced'),
        ('path_adjusted', 'Path Adjusted'),
    ])
    
    # What changed
    old_value = JSONField()
    new_value = JSONField()
    
    # Source
    source = CharField(max_length=20, choices=[
        ('gps', 'GPS Data'),
        ('driver', 'Driver Feedback'),
    ])
    
    applied = BooleanField(default=False)
    applied_at = DateTimeField(null=True)
```

#### 7. GPSTrackingPoint (Optional)
```python
class GPSTrackingPoint(models.Model):
    """GPS tracking during trip"""
    
    trip = ForeignKey(Trip, related_name='gps_points')
    
    latitude = DecimalField(max_digits=10, decimal_places=6)
    longitude = DecimalField(max_digits=10, decimal_places=6)
    timestamp = DateTimeField()
    speed_kmh = FloatField(null=True)
    
    is_stopped = BooleanField(default=False)
```

---

## Pricing System

### Auto-Calculation with Driver Override

**Flow:**
1. System auto-calculates prices based on distance
2. Driver previews stops with calculated prices
3. Driver can edit any stop price
4. Trip created with final prices

**Implementation:**

```python
def calculate_stop_prices(trip, stops_data, price_per_km=50):
    """
    Auto-calculate prices, driver can override
    """
    prices = []
    for i, stop in enumerate(stops_data):
        if i == 0:
            prices.append(0)  # Origin = 0
        else:
            distance = stop['distance_from_start_km']
            auto_price = int(distance * price_per_km)
            
            # Driver can override during preview
            final_price = stop.get('custom_price', auto_price)
            prices.append(final_price)
    
    return prices

def calculate_fare(from_stop, to_stop):
    """Calculate fare between two stops"""
    return to_stop.price_from_start - from_stop.price_from_start
```

**API Flow:**

```
POST /api/trips/preview/
Body: {
  "from_city": 1,
  "to_city": 5,
  "selected_route_index": 0
}

Response: {
  "stops": [
    {"city": "Sanaa", "distance": 0, "auto_price": 0},
    {"city": "Dhamar", "distance": 98, "auto_price": 4900},
    {"city": "Ibb", "distance": 165, "auto_price": 8250},
    {"city": "Taiz", "distance": 256, "auto_price": 12800}
  ]
}

# Driver edits prices, then:

POST /api/trips/create/
Body: {
  "stops": [
    {"city_id": 1, "distance": 0, "price": 0},
    {"city_id": 2, "distance": 98, "price": 5000},  # Edited
    {"city_id": 3, "distance": 165, "price": 9000},  # Edited
    {"city_id": 5, "distance": 256, "price": 13000}  # Edited
  ]
}
```

---

## Seat Availability Logic

### Current (Broken)
```python
AllTrips.available_seats = 40  # All share same value ❌
```

### New (Correct)
```python
# Seat matrix per segment
Trip.seat_matrix = {
    "0-1": 40,  # Segment 0→1
    "1-2": 40,  # Segment 1→2
    "2-3": 40,  # Segment 2→3
}

# Booking from Stop 0 to Stop 2:
segments_crossed = ["0-1", "1-2"]
min_seats = min(seat_matrix[seg] for seg in segments_crossed)  # 40

# Book 1 passenger:
for seg in segments_crossed:
    seat_matrix[seg] -= 1

# Result: {"0-1": 39, "1-2": 39, "2-3": 40} ✅
```

---

## Phase 1: Core Fix (Week 1-3)

### Goal
Fix seat bug, optimize database, keep Google Maps

### Changes

1. **Add new models** (migrations)
2. **Refactor trip creation**:
   - Use `TripStop` instead of `AllTrips`
   - Store `seat_matrix` instead of single value
   - Keep polyline detection logic
3. **Update booking logic**:
   - Calculate crossed segments
   - Reduce seats on all segments
4. **Dynamic search**:
   - Query trips, not pre-computed sub-trips
   - Calculate availability on-the-fly

### Implementation

```python
# Trip creation (simplified)
def create_trip(from_city, to_city, selected_route, departure_time):
    # 1. Get Google Maps route
    polyline = selected_route['overview_polyline']['points']
    
    # 2. Detect stops (existing logic)
    stops = detect_stops_on_polyline(polyline, from_city, to_city)
    
    # 3. Create trip
    trip = Trip.objects.create(
        from_city=from_city,
        to_city=to_city,
        journey_date=departure_time.date(),
        planned_polyline=polyline,
        planned_route_name=selected_route['summary'],
        seat_matrix=initialize_seat_matrix(len(stops))
    )
    
    # 4. Create stops
    for i, stop_city in enumerate(stops):
        TripStop.objects.create(
            trip=trip,
            city=stop_city,
            sequence=i,
            planned_arrival=calculate_time(i),
            distance_from_start_km=calculate_distance(i)
        )
    
    return trip

# Seat matrix initialization
def initialize_seat_matrix(num_stops):
    matrix = {}
    for i in range(num_stops - 1):
        matrix[f"{i}-{i+1}"] = 40  # Bus capacity
    return matrix
```

### Deliverables
- ✅ Correct seat tracking
- ✅ 52% fewer database records
- ✅ Production ready in 3 weeks

---

## Phase 2: Route Learning (Week 4-11)

### Goal
Build centralized route database from real trips

### Flow

#### 1. First Time Route
```
Driver: "Sanaa → Taiz, Highway"
  ↓
Check database for template
  ↓
Not found → Call Google Maps
  ↓
Create RouteTemplate (unverified)
  ↓
Create Trip (links to template)
  ↓
Template.times_used = 1
```

#### 2. During Trip
```
GPS tracking (every 30 seconds)
  ↓
Store GPSTrackingPoint records
  ↓
Driver feedback: "Stopped at Yarim, not Dhamar"
  ↓
Store correction
```

#### 3. After Trip
```
Trip completes
  ↓
Generate actual_polyline from GPS
  ↓
Compare with planned route
  ↓
If different > 15%:
  - Create RouteCorrection
  - Mark template for review
  ↓
Update template statistics
  ↓
If times_used >= 3:
  - Mark as verified
```

#### 4. Next Time
```
Driver: "Sanaa → Taiz, Highway"
  ↓
Check database
  ↓
Found verified template!
  ↓
Show template with corrections
  ↓
Create trip using template
  ↓
Template.times_used += 1
```

### Correction Logic

```python
def analyze_trip_corrections(trip):
    """Compare planned vs actual route"""
    
    # Get GPS data
    gps_points = trip.gps_points.all()
    actual_polyline = encode_gps_to_polyline(gps_points)
    
    # Detect actual stops (speed < 5 km/h for > 2 min)
    actual_stops = detect_stops_from_gps(gps_points)
    
    # Compare with planned
    planned_stops = [stop.city.name for stop in trip.stops.all()]
    
    # Find differences
    for i, (planned, actual) in enumerate(zip(planned_stops, actual_stops)):
        if planned != actual:
            RouteCorrection.objects.create(
                route_template=trip.route_template,
                trip=trip,
                correction_type='stop_replaced',
                old_value={'stop': planned, 'sequence': i},
                new_value={'stop': actual, 'sequence': i},
                source='gps'
            )

def apply_corrections():
    """Daily task: Apply verified corrections"""
    
    # Find corrections that appear 3+ times
    corrections = RouteCorrection.objects.filter(
        applied=False
    ).values(
        'route_template', 'old_value', 'new_value'
    ).annotate(
        count=Count('id')
    ).filter(count__gte=3)
    
    for correction in corrections:
        # Update template
        template = RouteTemplate.objects.get(id=correction['route_template'])
        old_stop = template.stops.get(city__name=correction['old_value']['stop'])
        old_stop.city = City.objects.get(name=correction['new_value']['stop'])
        old_stop.confidence = 0.9
        old_stop.save()
        
        # Mark as applied
        RouteCorrection.objects.filter(
            route_template=template,
            old_value=correction['old_value']
        ).update(applied=True)
```

### Route Suggestions (Simple)

```python
def suggest_routes(from_city, to_city):
    """Show routes sorted by usage (no ML)"""
    
    # Get all templates
    templates = RouteTemplate.objects.filter(
        from_city=from_city,
        to_city=to_city,
        is_active=True
    ).order_by('-times_used')  # Most used first
    
    if not templates.exists():
        # Fallback to Google Maps
        return get_google_maps_routes(from_city, to_city)
    
    # Format response
    suggestions = []
    for template in templates:
        suggestions.append({
            'id': template.id,
            'name': template.name,
            'distance_km': template.distance_km,
            'stops': [stop.city.name for stop in template.stops.all()],
            'times_used': template.times_used,
            'success_rate': template.success_rate,
            'is_verified': template.is_verified,
            'source': template.source,
        })
    
    return suggestions
```

### Deliverables
- ✅ GPS tracking system
- ✅ Route template database
- ✅ Frequency-based suggestions
- ✅ Self-correcting routes

---

## API Changes

### New Endpoints

#### 1. Route Suggestions
```
GET /api/routes/suggest/?from=1&to=5

Response:
{
  "suggestions": [
    {
      "id": 123,
      "name": "Highway Route",
      "distance_km": 256,
      "stops": ["Sanaa", "Dhamar", "Ibb", "Taiz"],
      "times_used": 15,
      "success_rate": 0.93,
      "is_verified": true,
      "source": "gps"
    }
  ],
  "has_google_fallback": true
}
```

#### 2. GPS Tracking
```
POST /api/trips/123/gps/
Body: {
  "points": [
    {"lat": 15.3694, "lng": 44.1910, "timestamp": "...", "speed": 80}
  ]
}
```

#### 3. Driver Feedback
```
POST /api/trips/123/feedback/
Body: {
  "issue_type": "wrong_stop",
  "expected": "Dhamar",
  "actual": "Yarim",
  "comment": "Highway goes through Yarim"
}
```

### Modified Endpoints

#### Trip Search (No breaking changes)
```
GET /api/trips/bus-list/?pickup=Sanaa&destination=Taiz&date=2024-01-15

Response: (Same structure, correct seats)
{
  "results": [
    {
      "id": 456,
      "available_seats": 38,  # Now correct!
      "stops": ["Sanaa", "Dhamar", "Ibb", "Taiz"]
    }
  ]
}
```

---

## Migration Strategy

### Step 1: Add Models
```bash
python manage.py makemigrations
python manage.py migrate
```

### Step 2: Dual System (1 week)
- Feature flag: `USE_NEW_SYSTEM = True`
- New trips use new models
- Old trips still work

### Step 3: Data Migration
```python
# Migrate MainTrip → Trip
# Migrate AllTrips (segments only) → TripStop
# Calculate seat_matrix
```

### Step 4: Deprecate Old Models
- Keep for 3 months
- Archive old data

---

## Performance Comparison

### Database Records

**6-stop route, 10 trips:**

| System | Records | Savings |
|--------|---------|---------|
| Current | 160 | - |
| New | 77 | 52% |

### Query Performance

**Current**: Simple but wrong
**New**: Slightly complex but correct
**Optimization**: Redis caching

---

## Testing Strategy

### Unit Tests
- [ ] Seat matrix calculation
- [ ] Segment seat reduction
- [ ] Route similarity (85% threshold)
- [ ] Correction detection

### Integration Tests
- [ ] Trip creation flow
- [ ] Multi-segment booking
- [ ] Cancellation (seat release)
- [ ] GPS tracking

### Load Tests
- [ ] 1000 concurrent searches
- [ ] 100 simultaneous bookings

---

## Timeline

### Week 1-2: Phase 1 Development
- Create models
- Refactor trip creation
- Update booking logic
- Write tests

### Week 3: Testing & Deployment
- QA testing
- Deploy to production
- Monitor

### Week 4-6: Phase 2 Development
- GPS tracking API
- Route template creation
- Correction detection

### Week 7-9: Learning System
- Apply corrections
- Route suggestions
- Driver feedback UI

### Week 10-11: Polish & Optimize
- Performance tuning
- Bug fixes
- Documentation

---

## Success Metrics

### Phase 1
- ✅ 0 seat bugs
- ✅ < 200ms search time
- ✅ 100% booking success

### Phase 2
- ✅ 50+ route templates
- ✅ 80% GPS coverage
- ✅ 90% driver satisfaction

---

## Dependencies

### External Services
- Google Maps API
- Redis (caching)
- Celery (async tasks)

### Python Packages
```
googlemaps==4.10.0
polyline==2.0.0
shapely==2.0.0
geopy==2.3.0
scipy==1.11.0  # For route similarity
```

### Infrastructure
- PostgreSQL with JSONB
- Mobile app (GPS tracking)

---

## Key Differences from Previous Plan

### Removed
- ❌ ML scoring algorithms
- ❌ Feature engineering
- ❌ Model training
- ❌ Complex analytics
- ❌ RouteAnalytics model

### Simplified
- ✅ Frequency-based suggestions (not ML)
- ✅ Simple correction logic (not complex scoring)
- ✅ GPS + driver feedback (not ML pipeline)
- ✅ 11 weeks total (not 6+ months)

### Result
- **50% less complexity**
- **40% less time**
- **Same benefits**
- **Production ready faster**

---

## Conclusion

This refactoring plan focuses on **practical, proven techniques**:

1. Fix the seat bug (critical)
2. Learn from real trips (GPS + feedback)
3. Build route database (frequency-based)
4. Suggest popular routes (simple sorting)

**No ML needed** - just good engineering!

---

**Document Version**: 3.0  
**Last Updated**: 2024  
**Status**: ✅ Ready for Implementation
