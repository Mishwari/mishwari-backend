from django.contrib import admin
from django import forms
from django.core.exceptions import ValidationError
from .models import (
    Driver, Trip, CityList, TripStop, Booking, Seat, Bus, BusOperator,
    Passenger, OTPAttempt, Profile, OperatorMetrics, UpgradeRequest,
    DriverInvitation, TripReview
)

# Customize admin site
admin.site.site_header = "YallaBus Administration"
admin.site.site_title = "YallaBus Admin"
admin.site.index_title = "Welcome to YallaBus Admin Panel"

@admin.register(Driver)
class DriverAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'get_username', 'operator', 'driver_rating']
    list_filter = ['operator']
    search_fields = ['user__username', 'user__email', 'user__first_name', 'user__last_name', 'operator__name']
    ordering = ['id']
    list_per_page = 50
    
    def get_username(self, obj):
        return obj.user.username
    get_username.short_description = 'Username'
    get_username.admin_order_field = 'user__username'


@admin.register(Trip)
class TripAdmin(admin.ModelAdmin):
    list_display = ['id', 'from_city', 'to_city', 'journey_date', 'status', 'operator', 'bus', 'driver', 'created_at']
    list_filter = ['status', 'journey_date', 'operator', 'created_at']
    search_fields = ['from_city__city', 'to_city__city', 'operator__name', 'planned_route_name']
    ordering = ['-journey_date', '-created_at']
    date_hierarchy = 'journey_date'
    list_per_page = 50
    readonly_fields = ['created_at']
    autocomplete_fields = ['from_city', 'to_city', 'operator', 'bus', 'driver']
    actions = ['submit_to_google_index', 'remove_from_google_index']
    
    def submit_to_google_index(self, request, queryset):
        from .utils.google_indexing import notify_google_indexing
        import os
        site_url = os.getenv('SITE_URL', 'https://yallabus.app')
        success = 0
        for trip in queryset:
            trip_url = f'{site_url}/bus_list/{trip.id}'
            if notify_google_indexing(trip_url, 'URL_UPDATED'):
                success += 1
        self.message_user(request, f"{success}/{queryset.count()} trips submitted to Google Index.")
    submit_to_google_index.short_description = "Submit to Google Index"
    
    def remove_from_google_index(self, request, queryset):
        from .utils.google_indexing import notify_google_indexing
        import os
        site_url = os.getenv('SITE_URL', 'https://yallabus.app')
        success = 0
        for trip in queryset:
            trip_url = f'{site_url}/bus_list/{trip.id}'
            if notify_google_indexing(trip_url, 'URL_DELETED'):
                success += 1
        self.message_user(request, f"{success}/{queryset.count()} trips removed from Google Index.")
    remove_from_google_index.short_description = "Remove from Google Index"


@admin.register(TripStop)
class TripStopAdmin(admin.ModelAdmin):
    list_display = ['id', 'trip', 'city', 'sequence', 'planned_arrival', 'planned_departure', 'distance_from_start_km', 'price_from_start']
    list_filter = ['trip__journey_date', 'city']
    search_fields = ['trip__id', 'city__city', 'trip__from_city__city', 'trip__to_city__city']
    ordering = ['trip', 'sequence']
    list_per_page = 100
    autocomplete_fields = ['trip', 'city']


@admin.register(CityList)
class CityListAdmin(admin.ModelAdmin):
    list_display = ['id', 'city', 'latitude', 'longitude']
    search_fields = ['city']
    ordering = ['city']
    list_per_page = 100


class BookingAdminForm(forms.ModelForm):
    class Meta:
        model = Booking
        fields = '__all__'

    def clean_seats(self):
        seats = self.cleaned_data.get('seats')
        trip = self.cleaned_data.get('trip')

        if not trip:
            raise ValidationError("You must select a trip before choosing seats.")

        for seat in seats:
            if seat.trip is None:
                raise ValidationError(f"Seat {seat.seat_number} is not associated with any trip.")
            if seat.trip != trip:
                raise ValidationError("All selected seats must belong to the selected trip.")

        return seats


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    form = BookingAdminForm
    list_display = ['id', 'user', 'get_from_city', 'get_to_city', 'trip', 'total_fare', 'status', 'is_paid', 'payment_method', 'booking_source', 'booking_time']
    list_filter = ['status', 'is_paid', 'payment_method', 'booking_source', 'booking_time', 'trip__journey_date']
    search_fields = ['user__username', 'user__email', 'trip__id', 'contact_name', 'contact_phone', 'contact_email']
    ordering = ['-booking_time']
    date_hierarchy = 'booking_time'
    list_per_page = 50
    readonly_fields = ['booking_time', 'total_fare']
    autocomplete_fields = ['user', 'trip', 'from_stop', 'to_stop']
    
    def get_from_city(self, obj):
        return obj.from_stop.city.city if obj.from_stop else '-'
    get_from_city.short_description = 'From'
    
    def get_to_city(self, obj):
        return obj.to_stop.city.city if obj.to_stop else '-'
    get_to_city.short_description = 'To'


@admin.register(Seat)
class SeatAdmin(admin.ModelAdmin):
    list_display = ['id', 'trip', 'seat_number', 'available_segments', 'get_journey_date']
    list_filter = ['trip__journey_date', 'trip__status']
    search_fields = ['trip__id', 'seat_number', 'trip__from_city__city', 'trip__to_city__city']
    ordering = ['trip', 'seat_number']
    list_per_page = 100
    autocomplete_fields = ['trip']
    
    def get_journey_date(self, obj):
        return obj.trip.journey_date
    get_journey_date.short_description = 'Journey Date'
    get_journey_date.admin_order_field = 'trip__journey_date'


@admin.register(Bus)
class BusAdmin(admin.ModelAdmin):
    list_display = ['id', 'operator', 'bus_number', 'bus_type', 'capacity', 'is_verified', 'has_ac', 'has_wifi', 'has_usb_charging', 'avg_rating']
    list_filter = ['is_verified', 'bus_type', 'has_ac', 'has_wifi', 'has_usb_charging', 'operator']
    search_fields = ['operator__name', 'bus_number', 'bus_type']
    ordering = ['id']
    list_per_page = 50
    readonly_fields = ['avg_rating']
    autocomplete_fields = ['operator']
    actions = ['verify_buses', 'unverify_buses']
    
    def verify_buses(self, request, queryset):
        queryset.update(is_verified=True)
        self.message_user(request, f"{queryset.count()} buses verified.")
    verify_buses.short_description = "Verify selected buses"
    
    def unverify_buses(self, request, queryset):
        queryset.update(is_verified=False)
        self.message_user(request, f"{queryset.count()} buses unverified.")
    unverify_buses.short_description = "Unverify selected buses"


@admin.register(BusOperator)
class BusOperatorAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'contact_info', 'uses_own_system', 'is_verified', 'platform_user', 'get_bus_count']
    list_filter = ['is_verified', 'uses_own_system']
    search_fields = ['name', 'contact_info', 'platform_user__username', 'platform_user__email']
    ordering = ['id']
    list_per_page = 50
    autocomplete_fields = ['platform_user']
    actions = ['verify_operators', 'unverify_operators']
    
    def get_bus_count(self, obj):
        return obj.buses.count()
    get_bus_count.short_description = 'Buses'
    
    def verify_operators(self, request, queryset):
        queryset.update(is_verified=True)
        self.message_user(request, f"{queryset.count()} operators verified.")
    verify_operators.short_description = "Verify selected operators"
    
    def unverify_operators(self, request, queryset):
        queryset.update(is_verified=False)
        self.message_user(request, f"{queryset.count()} operators unverified.")
    unverify_operators.short_description = "Unverify selected operators"


@admin.register(Passenger)
class PassengerAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'name', 'age', 'gender']
    list_filter = ['gender']
    search_fields = ['user__username', 'user__email', 'name']
    ordering = ['id']
    list_per_page = 100
    autocomplete_fields = ['user']


@admin.register(OTPAttempt)
class OTPAttemptAdmin(admin.ModelAdmin):
    list_display = ['id', 'mobile_number', 'attempt_count', 'last_attempt', 'blocked_until', 'is_blocked']
    list_filter = ['last_attempt', 'blocked_until']
    search_fields = ['mobile_number']
    ordering = ['-last_attempt']
    date_hierarchy = 'last_attempt'
    list_per_page = 100
    readonly_fields = ['last_attempt']
    actions = ['unblock_numbers']
    
    def is_blocked(self, obj):
        from django.utils import timezone
        return obj.blocked_until and obj.blocked_until > timezone.now()
    is_blocked.boolean = True
    is_blocked.short_description = 'Blocked'
    
    def unblock_numbers(self, request, queryset):
        queryset.update(blocked_until=None, attempt_count=0)
        self.message_user(request, f"{queryset.count()} numbers unblocked.")
    unblock_numbers.short_description = "Unblock selected numbers"


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'get_email', 'mobile_number', 'full_name', 'role', 'is_verified', 'created_at']
    list_filter = ['role', 'is_verified', 'created_at']
    search_fields = ['user__username', 'user__email', 'mobile_number', 'full_name']
    ordering = ['-created_at']
    date_hierarchy = 'created_at'
    list_per_page = 50
    readonly_fields = ['created_at']
    autocomplete_fields = ['user']
    actions = ['verify_profiles', 'unverify_profiles']
    
    def get_email(self, obj):
        return obj.user.email
    get_email.short_description = 'Email'
    get_email.admin_order_field = 'user__email'
    
    def verify_profiles(self, request, queryset):
        queryset.update(is_verified=True)
        self.message_user(request, f"{queryset.count()} profiles verified.")
    verify_profiles.short_description = "Verify selected profiles"
    
    def unverify_profiles(self, request, queryset):
        queryset.update(is_verified=False)
        self.message_user(request, f"{queryset.count()} profiles unverified.")
    unverify_profiles.short_description = "Unverify selected profiles"


@admin.register(OperatorMetrics)
class OperatorMetricsAdmin(admin.ModelAdmin):
    list_display = ['id', 'operator', 'health_score', 'cancellation_rate', 'strikes', 'is_suspended']
    list_filter = ['is_suspended']
    search_fields = ['operator__name']
    ordering = ['-health_score']
    list_per_page = 50
    autocomplete_fields = ['operator']
    actions = ['suspend_operators', 'unsuspend_operators', 'reset_strikes']
    
    def suspend_operators(self, request, queryset):
        queryset.update(is_suspended=True)
        self.message_user(request, f"{queryset.count()} operators suspended.")
    suspend_operators.short_description = "Suspend selected operators"
    
    def unsuspend_operators(self, request, queryset):
        queryset.update(is_suspended=False)
        self.message_user(request, f"{queryset.count()} operators unsuspended.")
    unsuspend_operators.short_description = "Unsuspend selected operators"
    
    def reset_strikes(self, request, queryset):
        queryset.update(strikes=0)
        self.message_user(request, f"Strikes reset for {queryset.count()} operators.")
    reset_strikes.short_description = "Reset strikes for selected operators"


@admin.register(UpgradeRequest)
class UpgradeRequestAdmin(admin.ModelAdmin):
    list_display = ['profile', 'company_name', 'status', 'created_at', 'reviewed_at']
    list_filter = ['status', 'created_at']
    search_fields = ['profile__full_name', 'company_name', 'commercial_registration']
    actions = ['approve_requests', 'reject_requests']
    readonly_fields = ['created_at', 'reviewed_at']
    
    def approve_requests(self, request, queryset):
        for upgrade_request in queryset.filter(status='pending'):
            upgrade_request.approve_upgrade()
        self.message_user(request, f"{queryset.count()} upgrade requests approved.")
    approve_requests.short_description = "Approve selected upgrade requests"
    
    def reject_requests(self, request, queryset):
        queryset.update(status='rejected')
        self.message_user(request, f"{queryset.count()} upgrade requests rejected.")
    reject_requests.short_description = "Reject selected upgrade requests"


@admin.register(DriverInvitation)
class DriverInvitationAdmin(admin.ModelAdmin):
    list_display = ['operator', 'mobile_number', 'invite_code', 'status', 'created_at', 'expires_at', 'accepted_at']
    list_filter = ['status', 'created_at']
    search_fields = ['operator__name', 'mobile_number', 'invite_code']
    readonly_fields = ['invite_code', 'created_at', 'accepted_at', 'accepted_by']
    actions = ['cancel_invitations']
    
    def cancel_invitations(self, request, queryset):
        queryset.filter(status='pending').update(status='cancelled')
        self.message_user(request, f"{queryset.count()} invitations cancelled.")
    cancel_invitations.short_description = "Cancel selected invitations"


@admin.register(TripReview)
class TripReviewAdmin(admin.ModelAdmin):
    list_display = ['id', 'booking', 'get_user', 'operator_snapshot', 'overall_rating', 'bus_condition_rating', 'driver_rating', 'created_at']
    list_filter = ['overall_rating', 'bus_condition_rating', 'driver_rating', 'created_at']
    search_fields = ['booking__id', 'booking__user__username', 'operator_snapshot__name', 'comment']
    ordering = ['-created_at']
    date_hierarchy = 'created_at'
    list_per_page = 50
    readonly_fields = ['booking', 'bus_snapshot', 'driver_snapshot', 'operator_snapshot', 'created_at']
    
    def get_user(self, obj):
        return obj.booking.user.username if obj.booking else '-'
    get_user.short_description = 'User'
    get_user.admin_order_field = 'booking__user__username'
