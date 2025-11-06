from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError

from .models import Bus, Trip, Booking, Driver, TripStop, Passenger, BookingPassenger, Seat
from .serializers import BusSerializer, TripsSerializer, BookingSerializer2
from .permissions import IsVerifiedOperator, IsOperatorOrAdmin
from .booking_utils import create_booking_atomic
from .notifications import send_departure_notification


class OperatorFleetViewSet(viewsets.ModelViewSet):
    """Operator fleet management"""
    serializer_class = BusSerializer
    permission_classes = [IsAuthenticated, IsOperatorOrAdmin]
    authentication_classes = [JWTAuthentication]
    
    def get_queryset(self):
        driver = Driver.objects.get(user=self.request.user)
        return Bus.objects.filter(operator=driver.operator)
    
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
        driver = Driver.objects.get(user=self.request.user)
        return Trip.objects.filter(operator=driver.operator)
    
    def create(self, request, *args, **kwargs):
        """Create trip as draft by default"""
        data = request.data.copy()
        if 'status' not in data:
            data['status'] = 'draft'
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


class DriverManagementViewSet(viewsets.ViewSet):
    """Driver verification and management"""
    permission_classes = [IsAuthenticated, IsOperatorOrAdmin]
    authentication_classes = [JWTAuthentication]
    
    @action(detail=True, methods=['post'])
    def verify(self, request, pk=None):
        """Upload driver verification documents"""
        try:
            driver = Driver.objects.get(pk=pk)
            
            # Check if requester is the operator
            requester_driver = Driver.objects.get(user=request.user)
            if driver.operator != requester_driver.operator:
                return Response({'error': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)
            
            # Store document URLs
            documents = request.data.get('documents', {})
            driver.verification_documents = documents
            driver.save()
            
            return Response({
                'message': 'Driver documents uploaded successfully. Pending review.',
                'driver_id': driver.id,
                'is_verified': driver.is_verified
            })
        except Driver.DoesNotExist:
            return Response({'error': 'Driver not found'}, status=status.HTTP_404_NOT_FOUND)
