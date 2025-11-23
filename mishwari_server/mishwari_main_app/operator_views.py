from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError

from .models import Bus, Trip, Booking, Driver, TripStop, Passenger, BookingPassenger, Seat, BusOperator, UpgradeRequest, CityList, Profile
from django.contrib.auth.models import User
from .serializers import BusSerializer, TripsSerializer, BookingSerializer2, DriverSerializer
from .permissions import IsVerifiedOperator, IsOperatorOrAdmin
from .booking_utils import create_booking_atomic
from .notifications import send_departure_notification
from .route_utils import (
    cache_route_session, 
    get_cached_route_session,
    clear_route_session,
    get_google_maps_client,
    detect_waypoints_from_polyline
)
from .trip_creation_utils import create_trip_from_cached_route
from .operator_utils import get_operator_for_user
import polyline


class OperatorFleetViewSet(viewsets.ModelViewSet):
    """Operator fleet management"""
    serializer_class = BusSerializer
    permission_classes = [IsAuthenticated, IsOperatorOrAdmin]
    authentication_classes = [JWTAuthentication]
    
    def create(self, request, *args, **kwargs):
        """Create bus with role-based validation"""
        profile = request.user.profile
        operator = get_operator_for_user(request.user)
        
        # Limit individual drivers to 1 bus
        if profile.role == 'driver':
            existing_buses = Bus.objects.filter(operator=operator).count()
            
            if existing_buses >= 1:
                return Response({
                    'error': 'Individual drivers can only register one bus',
                    'message': 'Upgrade to operator account to add multiple buses',
                    'upgrade_url': '/upgrade'
                }, status=status.HTTP_403_FORBIDDEN)
        
        return super().create(request, *args, **kwargs)
    
    def perform_create(self, serializer):
        """Set operator when creating bus"""
        operator = get_operator_for_user(self.request.user)
        serializer.save(operator=operator)
    
    def update(self, request, *args, **kwargs):
        """Override update to uncheck is_verified when bus_number or bus_type changes"""
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        
        # Uncheck is_verified only if bus_number or bus_type changed
        if ('bus_number' in serializer.validated_data and serializer.validated_data['bus_number'] != instance.bus_number) or \
           ('bus_type' in serializer.validated_data and serializer.validated_data['bus_type'] != instance.bus_type):
            serializer.validated_data['is_verified'] = False
        
        self.perform_update(serializer)
        return Response(serializer.data)
    
    def partial_update(self, request, *args, **kwargs):
        """Override partial_update to uncheck is_verified when bus_number or bus_type changes"""
        kwargs['partial'] = True
        return self.update(request, *args, **kwargs)
    
    def get_queryset(self):
        operator = get_operator_for_user(self.request.user)
        return Bus.objects.filter(operator=operator)
    
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
        operator = get_operator_for_user(self.request.user)
        queryset = Trip.objects.filter(operator=operator)
        
        # Filter by status if provided
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        return queryset
    
    def create(self, request, *args, **kwargs):
        """Create trip with role-based validation"""
        profile = request.user.profile
        operator = get_operator_for_user(request.user)
        
        # Enforce trip limit for individual drivers
        if profile.role == 'driver':
            active_trips = Trip.objects.filter(
                operator=operator,
                status__in=['draft', 'published', 'active']
            ).count()
            
            trip_limit = getattr(operator.metrics, 'trip_limit', 2) if hasattr(operator, 'metrics') else 2
            
            if active_trips >= trip_limit:
                return Response({
                    'error': f'Trip limit reached ({trip_limit} concurrent trips)',
                    'message': 'Complete or cancel existing trips, or upgrade your account',
                    'current_trips': active_trips,
                    'limit': trip_limit
                }, status=status.HTTP_403_FORBIDDEN)
        
        data = request.data.copy()
        if 'status' not in data:
            data['status'] = 'draft'
        
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
    
    @action(detail=False, methods=['get'], url_path='detect-routes')
    def detect_routes(self, request):
        """Get route alternatives with summary (caches full response). GET /operator/trips/detect-routes/?from_city=1&to_city=5"""
        from_city_id = request.query_params.get('from_city')
        to_city_id = request.query_params.get('to_city')
        
        if not from_city_id or not to_city_id:
            return Response(
                {'error': 'from_city and to_city required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            from_city = CityList.objects.get(id=from_city_id)
            to_city = CityList.objects.get(id=to_city_id)
        except CityList.DoesNotExist:
            return Response(
                {'error': 'Invalid city ID'}, 
                status=status.HTTP_404_NOT_FOUND
            )
        
        try:
            gmaps = get_google_maps_client()
            routes = gmaps.directions(
                f"{from_city.latitude},{from_city.longitude}",
                f"{to_city.latitude},{to_city.longitude}",
                mode='driving',
                alternatives=True
            )
            
            if not routes:
                return Response(
                    {'error': 'No routes found between cities'}, 
                    status=status.HTTP_404_NOT_FOUND
                )
        except Exception as e:
            return Response(
                {'error': f'Google Maps API error: {str(e)}'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        session_id = cache_route_session(from_city, to_city, routes)
        
        routes_summary = [
            {
                'route_index': idx,
                'summary': route.get('summary', f'Route {idx + 1}'),
                'distance_km': route['legs'][0]['distance']['value'] / 1000,
                'duration_min': route['legs'][0]['duration']['value'] / 60,
                'polyline': route['overview_polyline']['points']
            }
            for idx, route in enumerate(routes)
        ]
        
        return Response({
            'session_id': session_id,
            'from_city': {'id': from_city.id, 'name': from_city.city},
            'to_city': {'id': to_city.id, 'name': to_city.city},
            'routes': routes_summary
        })
    
    @action(detail=False, methods=['get'], url_path='detect-waypoints')
    def detect_waypoints(self, request):
        """Get waypoints for selected route (uses cached data). GET /operator/trips/detect-waypoints/?session_id=uuid&route_index=0"""
        session_id = request.query_params.get('session_id')
        route_index = request.query_params.get('route_index')
        
        if not session_id or route_index is None:
            return Response(
                {'error': 'session_id and route_index required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        cached_data = get_cached_route_session(session_id)
        if not cached_data:
            return Response(
                {'error': 'Session expired. Please select route again.'}, 
                status=status.HTTP_404_NOT_FOUND
            )
        
        try:
            route_index = int(route_index)
            selected_route = cached_data['routes'][route_index]
        except (ValueError, IndexError):
            return Response(
                {'error': 'Invalid route_index'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        polyline_points = polyline.decode(selected_route['overview_polyline']['points'])
        
        from_city = CityList.objects.get(id=cached_data['from_city']['id'])
        to_city = CityList.objects.get(id=cached_data['to_city']['id'])
        
        waypoints = detect_waypoints_from_polyline(polyline_points, from_city, to_city)
        
        # Calculate total distance for the route
        total_distance = selected_route['legs'][0]['distance']['value'] / 1000
        
        return Response({
            'route_index': route_index,
            'route_summary': selected_route.get('summary', f'Route {route_index + 1}'),
            'total_distance_km': total_distance,
            'total_duration_min': selected_route['legs'][0]['duration']['value'] / 60,
            'waypoints': waypoints
        })
    
    @action(detail=True, methods=['get'])
    def bookings(self, request, pk=None):
        """Get bookings for a specific trip"""
        trip = self.get_object()
        bookings = Booking.objects.filter(trip=trip).order_by('-booking_time')
        serializer = BookingSerializer2(bookings, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['post'], url_path='create-with-stops')
    def create_with_stops(self, request):
        """Create trip using cached route data. POST /operator/trips/create-with-stops/"""
        session_id = request.data.get('session_id')
        route_index = request.data.get('route_index')
        
        if not session_id or route_index is None:
            return Response(
                {'error': 'session_id and route_index required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        cached_data = get_cached_route_session(session_id)
        if not cached_data:
            return Response(
                {'error': 'Session expired. Please select route again.'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            selected_route = cached_data['routes'][int(route_index)]
            
            operator = get_operator_for_user(request.user)
            
            # Get driver - either from request data (operator_admin) or current user (individual driver)
            driver_id = request.data.get('driver')
            if driver_id:
                driver = Driver.objects.get(id=driver_id, operator=operator)
            else:
                driver = Driver.objects.filter(user=request.user).first()
            
            bus = Bus.objects.get(id=request.data['bus'], operator=operator)
            
            trip = create_trip_from_cached_route(
                operator=operator,
                bus=bus,
                driver=driver,
                cached_data=cached_data,
                selected_route=selected_route,
                trip_data=request.data,
                selected_waypoint_ids=request.data.get('selected_waypoints', []),
                custom_prices=request.data.get('custom_prices', {})
            )
            
            # Auto-publish if requested and golden rule is satisfied
            auto_publish = request.data.get('auto_publish', False)
            if auto_publish and trip.can_publish():
                trip.status = 'published'
                trip.full_clean()
                trip.save()
            
            clear_route_session(session_id)
            
            serializer = self.get_serializer(trip)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
            
        except Bus.DoesNotExist:
            return Response({'error': 'Bus not found or not owned by operator'}, status=status.HTTP_404_NOT_FOUND)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)



class PhysicalBookingViewSet(viewsets.ModelViewSet):
    """Physical bookings made by operators"""
    serializer_class = BookingSerializer2
    permission_classes = [IsAuthenticated, IsOperatorOrAdmin]
    authentication_classes = [JWTAuthentication]
    
    def get_queryset(self):
        return Booking.objects.filter(booking_source='physical', created_by=self.request.user)
    
    def create(self, request):
        """Create physical booking"""
        trip_id = request.data.get('trip')
        
        # Verify operator owns this trip
        operator = get_operator_for_user(request.user)
        try:
            trip = Trip.objects.get(id=trip_id, operator=operator)
        except Trip.DoesNotExist:
            return Response(
                {'error': 'Trip not found or you do not have permission to book for this trip'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        with transaction.atomic():
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
        operator = get_operator_for_user(self.request.user)
        return Driver.objects.filter(operator=operator)
    
    def create(self, request):
        """Create driver account (operator_admin only)"""
        if request.user.profile.role != 'operator_admin':
            return Response({'error': 'Only operator_admin can add drivers'}, status=status.HTTP_403_FORBIDDEN)
        
        mobile_number = request.data.get('mobile_number')
        full_name = request.data.get('full_name')
        national_id = request.data.get('national_id', '')
        driver_license = request.data.get('driver_license', '')
        email = request.data.get('email', '')
        
        if not mobile_number or not full_name:
            return Response({'error': 'mobile_number and full_name are required'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if mobile number already exists
        if Profile.objects.filter(mobile_number=mobile_number).exists():
            return Response({'error': 'Mobile number already registered'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            with transaction.atomic():
                # Create User
                username = f"driver_{mobile_number}"
                user = User.objects.create_user(username=username, email=email or '')
                
                # Create Profile
                profile = Profile.objects.create(
                    user=user,
                    mobile_number=mobile_number,
                    full_name=full_name,
                    role='driver'
                )
                
                # Create Driver
                operator = get_operator_for_user(request.user)
                driver = Driver.objects.create(
                    user=user,
                    profile=profile,
                    national_id=national_id,
                    driver_license=driver_license,
                    driver_rating=0.0,
                    operator=operator
                )
                
                serializer = self.get_serializer(driver)
                return Response(serializer.data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['post'])
    def invite(self, request):
        """Invite driver by phone number (operator_admin only) - Manual process for now"""
        if request.user.profile.role != 'operator_admin':
            return Response({'error': 'Only operator_admin can invite drivers'}, status=status.HTTP_403_FORBIDDEN)
        
        phone = request.data.get('phone')
        if not phone:
            return Response({'error': 'Phone number required'}, status=status.HTTP_400_BAD_REQUEST)
        
        # TODO: Implement SMS invitation system
        # For now, operators should add drivers manually
        return Response({
            'message': 'Driver invitation feature coming soon. Please add drivers manually for now.',
            'phone': phone
        }, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['post'])
    def verify(self, request, pk=None):
        """Upload driver verification documents"""
        driver = self.get_object()
        
        # Validate ownership - driver must belong to current operator
        operator = get_operator_for_user(request.user)
        if driver.operator != operator:
            return Response(
                {'error': 'You do not have permission to verify this driver'},
                status=status.HTTP_403_FORBIDDEN
            )
        
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
            return Response({
                'error': 'Only individual drivers can request upgrade'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Check if already has pending request
        existing = UpgradeRequest.objects.filter(user=request.user, status='pending').first()
        if existing:
            return Response({
                'error': 'You already have a pending upgrade request',
                'request_id': existing.id,
                'submitted_at': existing.created_at
            }, status=status.HTTP_400_BAD_REQUEST)
        
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
