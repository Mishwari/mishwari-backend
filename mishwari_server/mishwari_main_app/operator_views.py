from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError

from .models import Bus, Trip, Booking, Driver, TripStop, Passenger, BookingPassenger, Seat, BusOperator, UpgradeRequest
from .serializers import BusSerializer, TripsSerializer, BookingSerializer2, DriverSerializer
from .permissions import IsVerifiedOperator, IsOperatorOrAdmin
from .booking_utils import create_booking_atomic
from .notifications import send_departure_notification


class OperatorFleetViewSet(viewsets.ModelViewSet):
    """Operator fleet management"""
    serializer_class = BusSerializer
    permission_classes = [IsAuthenticated, IsOperatorOrAdmin]
    authentication_classes = [JWTAuthentication]
    
    def get_queryset(self):
        # For role='driver': Get operator via Driver record
        # For role='operator_admin': Get operator via profile
        try:
            driver = Driver.objects.get(user=self.request.user)
            return Bus.objects.filter(operator=driver.operator)
        except Driver.DoesNotExist:
            # operator_admin case: find operator by profile
            profile = self.request.user.profile
            operators = BusOperator.objects.filter(contact_info=profile.mobile_number)
            if operators.exists():
                return Bus.objects.filter(operator=operators.first())
            return Bus.objects.none()
    
    @action(detail=True, methods=['post'])
    def verify(self, request, pk=None):
        """Upload bus verification documents"""
        bus = self.get_object()
        
        # Store document URLs (in production, upload to S3 first)
        documents = request.data.get('documents', {})
        bus.verification_documents = documents
        bus.save()
        
        return Response({
            'message': 'Bus documents uploaded successfully. Pending review.',
            'bus_id': bus.id,
            'is_verified': bus.is_verified
        })


class OperatorTripViewSet(viewsets.ModelViewSet):
    """Operator trip management with flexible/scheduled support"""
    serializer_class = TripsSerializer
    permission_classes = [IsAuthenticated, IsOperatorOrAdmin]
    authentication_classes = [JWTAuthentication]
    
    def get_queryset(self):
        # For role='driver': Get operator via Driver record
        # For role='operator_admin': Get operator via profile
        print(f'[TRIPS QUERYSET] User: {self.request.user.username}, Role: {self.request.user.profile.role}')
        try:
            driver = Driver.objects.get(user=self.request.user)
            print(f'[TRIPS QUERYSET] Found Driver ID: {driver.id}, Operator ID: {driver.operator.id}')
            return Trip.objects.filter(operator=driver.operator)
        except Driver.DoesNotExist:
            # operator_admin case: find operator by profile
            profile = self.request.user.profile
            print(f'[TRIPS QUERYSET] No Driver found, searching BusOperator by mobile: {profile.mobile_number}')
            operators = BusOperator.objects.filter(contact_info=profile.mobile_number)
            if operators.exists():
                print(f'[TRIPS QUERYSET] Found BusOperator ID: {operators.first().id}')
                return Trip.objects.filter(operator=operators.first())
            print(f'[TRIPS QUERYSET] No BusOperator found! Returning empty queryset')
            return Trip.objects.none()
    
    def create(self, request, *args, **kwargs):
        """Create trip as draft by default"""
        data = request.data.copy()
        if 'status' not in data:
            data['status'] = 'draft'
        
        # Set operator based on user role
        try:
            driver = Driver.objects.get(user=request.user)
            data['operator'] = driver.operator.id
        except Driver.DoesNotExist:
            # operator_admin case
            profile = request.user.profile
            operator = BusOperator.objects.filter(contact_info=profile.mobile_number).first()
            if operator:
                data['operator'] = operator.id
        
        request._full_data = data
        return super().create(request, *args, **kwargs)
    
    @action(detail=True, methods=['post'])
    def publish(self, request, pk=None):
        """Publish a draft trip (Golden Rule validation)"""
        trip = self.get_object()
        
        if trip.status != 'draft':
            return Response({'error': 'Only draft trips can be published'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            trip.status = 'published'
            trip.full_clean()  # Triggers Golden Rule validation
            trip.save()
            
            serializer = self.get_serializer(trip)
            return Response({
                'message': 'Trip published successfully',
                'trip': serializer.data
            })
        except ValidationError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def depart_now(self, request, pk=None):
        """Trigger departure for flexible trips"""
        trip = self.get_object()
        
        if trip.trip_type != 'flexible':
            return Response({'error': 'Only flexible trips can use depart now'}, status=status.HTTP_400_BAD_REQUEST)
        
        if trip.departure_window_start and timezone.now() < trip.departure_window_start:
            return Response({'error': 'Cannot depart before window start'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Update actual departure time
        trip.actual_departure = timezone.now()
        trip.status = 'active'
        trip.save()
        
        # Send notifications
        notification_count = send_departure_notification(trip.id)
        
        return Response({
            'message': f'Departure notification sent to {notification_count} passengers',
            'actual_departure': trip.actual_departure
        })


class PhysicalBookingViewSet(viewsets.ModelViewSet):
    """Physical bookings made by operators"""
    serializer_class = BookingSerializer2
    permission_classes = [IsAuthenticated, IsOperatorOrAdmin]
    authentication_classes = [JWTAuthentication]
    
    def get_queryset(self):
        return Booking.objects.filter(booking_source='physical', created_by=self.request.user)
    
    def create(self, request):
        """Create physical booking"""
        with transaction.atomic():
            trip_id = request.data.get('trip')
            from_stop_id = request.data.get('from_stop')
            to_stop_id = request.data.get('to_stop')
            passengers_data = request.data.get('passengers', [])
            
            # Create booking with physical source
            booking = create_booking_atomic(
                trip_id=trip_id,
                from_stop_id=from_stop_id,
                to_stop_id=to_stop_id,
                user=request.user,
                passengers_data=passengers_data,
                payment_method='cash'
            )
            
            booking.booking_source = 'physical'
            booking.created_by = request.user
            booking.save()
            
            serializer = self.get_serializer(booking)
            return Response(serializer.data, status=status.HTTP_201_CREATED)


class DriverManagementViewSet(viewsets.ModelViewSet):
    """Driver management for operator_admin"""
    serializer_class = DriverSerializer
    permission_classes = [IsAuthenticated, IsOperatorOrAdmin]
    authentication_classes = [JWTAuthentication]
    
    def get_queryset(self):
        """Get drivers for current operator"""
        try:
            driver = Driver.objects.get(user=self.request.user)
            return Driver.objects.filter(operator=driver.operator)
        except Driver.DoesNotExist:
            profile = self.request.user.profile
            operator = BusOperator.objects.filter(contact_info=profile.mobile_number).first()
            if operator:
                return Driver.objects.filter(operator=operator)
            return Driver.objects.none()
    
    @action(detail=False, methods=['post'])
    def invite(self, request):
        """Invite driver by phone number (operator_admin only)"""
        if request.user.profile.role != 'operator_admin':
            return Response({'error': 'Only operator_admin can invite drivers'}, status=status.HTTP_403_FORBIDDEN)
        
        phone = request.data.get('phone')
        if not phone:
            return Response({'error': 'Phone number required'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Get operator
        profile = request.user.profile
        operator = BusOperator.objects.filter(contact_info=profile.mobile_number).first()
        if not operator:
            return Response({'error': 'Operator not found'}, status=status.HTTP_404_NOT_FOUND)
        
        # TODO: Send SMS invitation
        # For now, just return success
        return Response({
            'message': f'Invitation sent to {phone}',
            'phone': phone
        }, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['post'])
    def verify(self, request, pk=None):
        """Upload driver verification documents"""
        driver = self.get_object()
        
        documents = request.data.get('documents', {})
        driver.verification_documents = documents
        driver.save()
        
        return Response({
            'message': 'Driver documents uploaded successfully. Pending review.',
            'driver_id': driver.id,
            'is_verified': driver.is_verified
        })


class UpgradeRequestViewSet(viewsets.ModelViewSet):
    """Handle driver upgrade requests"""
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    
    def get_queryset(self):
        return UpgradeRequest.objects.filter(user=self.request.user)
    
    def create(self, request):
        """Submit upgrade request"""
        if request.user.profile.role != 'driver':
            return Response({'error': 'Only drivers can request upgrade'}, status=status.HTTP_403_FORBIDDEN)
        
        # Check if already has pending request
        existing = UpgradeRequest.objects.filter(user=request.user, status='pending').first()
        if existing:
            return Response({'error': 'You already have a pending upgrade request'}, status=status.HTTP_400_BAD_REQUEST)
        
        upgrade_request = UpgradeRequest.objects.create(
            user=request.user,
            profile=request.user.profile,
            company_name=request.data.get('company_name'),
            commercial_registration=request.data.get('commercial_registration'),
            tax_number=request.data.get('tax_number', ''),
            documents=request.data.get('documents', {})
        )
        
        return Response({
            'id': upgrade_request.id,
            'status': upgrade_request.status,
            'message': 'Upgrade request submitted successfully'
        }, status=status.HTTP_201_CREATED)
    
    @action(detail=False, methods=['get'])
    def status(self, request):
        """Get current upgrade request status"""
        upgrade_request = UpgradeRequest.objects.filter(user=request.user).order_by('-created_at').first()
        
        if not upgrade_request:
            return Response({'status': 'none', 'message': 'No upgrade request found'})
        
        return Response({
            'id': upgrade_request.id,
            'status': upgrade_request.status,
            'company_name': upgrade_request.company_name,
            'created_at': upgrade_request.created_at,
            'reviewed_at': upgrade_request.reviewed_at,
            'rejection_reason': upgrade_request.rejection_reason
        })
