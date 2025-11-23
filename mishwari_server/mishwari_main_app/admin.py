from django.contrib import admin
from django import forms
from django.core.exceptions import ValidationError
from .models import Driver,Trip,CityList,TripStop,Booking,Seat,Bus,BusOperator,Passenger,BookingPassenger,TemporaryMobileVerification,Profile,OperatorMetrics,UpgradeRequest

@admin.register(Driver)
class DriverAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "operator", "driver_rating"]

    # def username(self, obj):
    #     return obj.user.username
    # username.admin_order_field = 'user__username'  # Allows column order sorting
    # username.short_description = 'Username'  # Renames column head


admin.site.register(Trip)
admin.site.register(TripStop)

admin.site.register(CityList)

# admin.site.register(Booking)


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
                # Handle the case where a seat does not have an associated trip
                raise ValidationError(f"Seat {seat.seat_number} is not associated with any trip.")
            if seat.trip != trip:
                raise ValidationError("All selected seats must belong to the selected trip.")

        return seats
    

@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    form = BookingAdminForm
    list_display = ['user', 'trip', 'booking_time', 'is_paid','status']
    search_fields = ['user__username', 'trip__id']

    # def save_model(self, request, obj, form, change):
    #     if form.is_valid():
    #         obj.save()

# admin.site.register(Seat)
@admin.register(Seat)
class SeatAdmin(admin.ModelAdmin):
    list_display = ['trip', 'seat_number', 'available_segments']
    search_fields = ['trip__id', 'seat_number']

# admin.site.register(Bus)
@admin.register(Bus)
class BusAdmin(admin.ModelAdmin):
    list_display = ['operator', 'bus_number', 'bus_type', 'capacity', 'is_verified']
    search_fields = ['operator__name', 'bus_number']

# admin.site.register(BusOperator)
@admin.register(BusOperator)
class BusOperatorAdmin(admin.ModelAdmin):
    list_display = ['name', 'contact_info', 'uses_own_system', 'is_verified', 'platform_user']
    search_fields = ['name', 'contact_info']

# admin.site.register(Passenger)
@admin.register(Passenger)
class PassengerAdmin(admin.ModelAdmin):
    list_display = ['user', 'name', 'phone', 'email', 'age', 'gender']
    search_fields = ['user__username', 'name', 'phone', 'email']

# admin.site.register(BookingPassenger)
@admin.register(BookingPassenger)
class BookingPassengerAdmin(admin.ModelAdmin):
    list_display = ['booking', 'passenger', 'seat', 'name', 'email', 'phone', 'age', 'gender']
    search_fields = ['booking__id', 'passenger__full_name', 'seat__seat_number']

# admin.site.register(TemporaryMobileVerification)
@admin.register(TemporaryMobileVerification)
class TemporaryMobileVerificationAdmin(admin.ModelAdmin):
    list_display = ['mobile_number', 'otp_code', 'is_verified', 'otp_sent_at', 'attempts']
    search_fields = ['mobile_number', 'otp_code']

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'mobile_number', 'full_name', 'role', 'is_verified', 'created_at']
    list_filter = ['role', 'is_verified']
    search_fields = ['user__username', 'mobile_number', 'full_name']
    actions = ['verify_operator']
    
    def verify_operator(self, request, queryset):
        queryset.update(is_verified=True)
        self.message_user(request, f"{queryset.count()} operators verified successfully.")
    verify_operator.short_description = "Verify selected operators"

@admin.register(OperatorMetrics)
class OperatorMetricsAdmin(admin.ModelAdmin):
    list_display = ['operator', 'health_score', 'cancellation_rate', 'strikes', 'is_suspended']
    list_filter = ['is_suspended']
    search_fields = ['operator__name']

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

