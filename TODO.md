# TODO - Optional Future Improvements

## Current Status: ✅ PRODUCTION READY

All critical refactoring is complete. The items below are **optional improvements** that can be done gradually.

---

## Optional Tasks (Non-Breaking)

### 1. Migrate models_legacy.py to Domain Files
- [x] Update models/__init__.py to import from domain files instead of models_legacy
- [x] Renamed models_legacy.py to .bak

### 2. Migrate serializers_legacy.py to Domain Files
- [x] Create serializers/user_serializers.py
- [x] Create serializers/operator_serializers.py
- [x] Create serializers/trip_serializers.py
- [x] Create serializers/booking_serializers.py
- [x] Create serializers/review_serializers.py
- [x] Update serializers/__init__.py
- [x] Renamed serializers_legacy.py to .bak

### 3. Split views.py into Domain Files
- [x] Create views/trip_views.py (TripSearchView, CitiesView, etc.)
- [x] Create views/booking_views.py (BookingViewSet, etc.)
- [x] Create views/user_views.py (UserViewSet, etc.)
- [x] Create views/route_views.py, review_views.py
- [x] Update views/__init__.py
- [x] Rename views.py to views_legacy.py
- [x] Migrate booking_views implementation
- [x] Migrate route_views implementation
- [x] Migrate review_views implementation

### 4. Update Views to Use Services Directly
- [x] Update BookingViewSet to use BookingService directly
- [x] Migrate all view implementations from views_legacy
- [ ] Update TripSearchView to use TripService (optional)

### 5. Add More Tests
- [ ] Add tests for TripService
- [ ] Add tests for PaymentService
- [ ] Add integration tests for API endpoints
- [ ] Add tests for serializers

---

## Notes

- **No rush** - Current code is production-ready
- **No breaking changes** - All migrations are backward compatible
- **Test after each step** - Ensure nothing breaks
- **Can be done incrementally** - One task at a time

---

## Priority

**Low Priority** - These are code quality improvements, not critical fixes.

Current structure is clean, maintainable, and fully functional.

## Recently Completed

### High Priority Tasks (Tasks 1-2)
- [x] Migrated serializers to domain files (user, operator, trip, booking, review)
- [x] Updated serializers/__init__.py to import from domain files
- [x] Migrated models/__init__.py to import from domain files
- [x] Deleted legacy files (models_legacy.py.bak, serializers_legacy.py.bak, views_legacy.py)

### Medium Priority Tasks
- [x] Created RouteService to extract route planning logic
- [x] Created NotificationService to centralize notification logic
- [x] Updated services/__init__.py with new services

### Views Migration (Task 4)
- [x] Migrated BookingViewSet to use BookingService.cancel_booking() directly
- [x] Migrated all booking views (BookingViewSet, BookingTripsViewSet, PassengersViewSet)
- [x] Migrated review views (TripReviewViewSet)
- [x] Migrated route views (RouteViewSet, TripsViewSet) with CacheKeys
- [x] Updated cache_keys.py with route-specific methods
- [x] All views now independent from views_legacy

### Cleanup
- [x] Fixed all import errors (admin.py, operator_views.py, user_views.py, trip_views.py)
- [x] Deleted unused legacy files
- [x] Verified all imports working
- [x] Moved utility files to utils/ (booking_utils, operator_utils, route_utils, trip_creation_utils)
- [x] Updated all imports to reflect new structure
