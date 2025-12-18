from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from datetime import timedelta

from ..models import Bus, Trip, Booking, Driver, TripStop, Passenger, Seat, BusOperator, UpgradeRequest, CityList, Profile, DriverInvitation
from django.contrib.auth.models import User
from ..serializers import BusSerializer, TripsSerializer, BookingSerializer, DriverSerializer
from ..permissions import IsVerifiedOperator, IsOperatorOrAdmin, require_transaction_auth
from ..utils.booking_utils import create_booking_atomic
from ..notifications import send_departure_notification
from ..utils.route_utils import (
    cache_route_session, 
    get_cached_route_session,
    clear_route_session,
    get_google_maps_client,
    detect_waypoints_from_polyline
)
from ..utils.trip_creation_utils import create_trip_from_cached_route
from ..utils.operator_utils import get_operator_for_user
import polyline


class OperatorFleetViewSet(viewsets.ModelViewSet):
    """Operator fleet management"""
    serializer_class = BusSerializer
    permission_classes = [IsAuthenticated, IsOperatorOrAdmin]
    authentication_classes = [JWTAuthentication]
    
    def list(self, request, *args, **kwargs):
        """List buses - read-only for invited drivers"""
        return super().list(request, *args, **kwargs)
    
    def retrieve(self, request, *args, **kwargs):
        """Get bus details - read-only for invited drivers"""
        return super().retrieve(request, *args, **kwargs)
    
    @require_transaction_auth
    def destroy(self, request, *args, **kwargs):
        """Delete bus - requires step-up auth"""
        return super().destroy(request, *args, **kwargs)
    
    def create(self, request, *args, **kwargs):
        """Create bus with role-based validation"""
        profile = request.user.profile
        operator = get_operator_for_user(request.user)
        
        # Invited drivers cannot create buses
        if profile.role == 'invited_driver':
            return Response({'error': 'Invited drivers cannot create buses'}, status=status.HTTP_403_FORBIDDEN)
        
        # Standalone drivers limited to 1 bus
        if profile.role == 'standalone_driver':
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
        """Update bus - operator_admin and standalone drivers"""
        profile = request.user.profile
        
        if profile.role == 'invited_driver':
            return Response({'error': 'Invited drivers cannot update buses'}, status=status.HTTP_403_FORBIDDEN)
        
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        
        if ('bus_number' in serializer.validated_data and serializer.validated_data['bus_number'] != instance.bus_number) or \
           ('bus_type' in serializer.validated_data and serializer.validated_data['bus_type'] != instance.bus_type):
            serializer.validated_data['is_verified'] = False
        
        self.perform_update(serializer)
        return Response(serializer.data)
    
    def partial_update(self, request, *args, **kwargs):
        """Partial update bus - operator_admin and standalone drivers"""
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
    
    @require_transaction_auth
    def destroy(self, request, *args, **kwargs):
        """Delete trip - requires step-up auth"""
        return super().destroy(request, *args, **kwargs)
    
    def get_queryset(self):
        operator = get_operator_for_user(self.request.user)
        queryset = Trip.objects.filter(operator=operator)
        
        # Invited drivers only see trips assigned to them
        if self.request.user.profile.role == 'invited_driver':
            queryset = queryset.filter(driver__user=self.request.user)
        
        # Filter by status if provided
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        return queryset
    
    def update(self, request, *args, **kwargs):
        """Update trip - operator_admin and standalone drivers"""
        profile = request.user.profile
        
        if profile.role == 'invited_driver':
            return Response({'error': 'Invited drivers cannot update trips'}, status=status.HTTP_403_FORBIDDEN)
        
        return super().update(request, *args, **kwargs)
    
    def partial_update(self, request, *args, **kwargs):
        """Partial update trip - operator_admin and standalone drivers"""
        kwargs['partial'] = True
        return self.update(request, *args, **kwargs)
    
    def create(self, request, *args, **kwargs):
        """Create trip - operator_admin and standalone drivers"""
        profile = request.user.profile
        operator = get_operator_for_user(request.user)
        
        if profile.role == 'invited_driver':
            return Response({'error': 'Invited drivers cannot create trips'}, status=status.HTTP_403_FORBIDDEN)
        
        # Enforce trip limit for standalone drivers
        if profile.role == 'standalone_driver':
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
        """Trigger departure - activate published trips"""
        trip = self.get_object()
        
        if trip.status != 'published':
            return Response({'error': 'Only published trips can be activated'}, status=status.HTTP_400_BAD_REQUEST)
        
        if trip.trip_type == 'flexible' and trip.departure_window_start and timezone.now() < trip.departure_window_start:
            return Response({'error': 'Cannot depart before window start'}, status=status.HTTP_400_BAD_REQUEST)
        
        trip.actual_departure = timezone.now()
        trip.status = 'active'
        trip.save()
        
        notification_count = send_departure_notification(trip.id)
        
        return Response({
            'message': f'Trip activated. Notification sent to {notification_count} passengers',
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
            print("ERROR", e)
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
        serializer = BookingSerializer(bookings, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'], url_path='set-actual-resources')
    def set_actual_resources(self, request, pk=None):
        """Set actual bus/driver if different from planned"""
        trip = self.get_object()
        profile = request.user.profile
        operator = get_operator_for_user(request.user)
        
        if profile.role == 'invited_driver':
            return Response({'error': 'Invited drivers cannot swap resources'}, 
                          status=status.HTTP_403_FORBIDDEN)
        
        actual_bus_id = request.data.get('actual_bus')
        actual_driver_id = request.data.get('actual_driver')
        
        try:
            if actual_bus_id:
                trip.actual_bus = Bus.objects.get(id=actual_bus_id, operator=operator)
            if actual_driver_id:
                trip.actual_driver = Driver.objects.get(id=actual_driver_id, operator=operator)
            
            trip.save()
            
            return Response({'message': 'Actual resources updated'})
        except (Bus.DoesNotExist, Driver.DoesNotExist):
            return Response({'error': 'Resource not found or not owned by operator'}, 
                          status=status.HTTP_404_NOT_FOUND)
    
    @action(detail=True, methods=['post'], url_path='complete')
    def complete_trip(self, request, pk=None):
        """Mark trip as completed and complete all its bookings"""
        trip = self.get_object()
        profile = request.user.profile
        
        if profile.role == 'standalone_driver':
            # Standalone driver can complete their own trips
            pass
        elif profile.role == 'invited_driver':
            # Invited driver can only complete assigned trips
            driver = Driver.objects.get(user=request.user)
            if trip.driver != driver and trip.actual_driver != driver:
                return Response({'error': 'Not your trip'}, status=status.HTTP_403_FORBIDDEN)
        elif profile.role != 'operator_admin':
            return Response({'error': 'Only drivers/operators can complete trips'}, status=status.HTTP_403_FORBIDDEN)
        
        if trip.status not in ['active', 'published']:
            return Response({'error': f'Cannot complete trip with status "{trip.status}"'}, status=status.HTTP_400_BAD_REQUEST)
        
        with transaction.atomic():
            trip.status = 'completed'
            trip.completed_at = timezone.now()
            trip.save()
            
            bookings = Booking.objects.filter(trip=trip).exclude(status__in=['cancelled', 'completed'])
            completed_count = bookings.update(status='completed')
        
        return Response({'message': 'Trip completed successfully', 'bookings_completed': completed_count}, status=status.HTTP_200_OK)
    
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
            
            clear_route_session(session_id)
            
            # Auto-publish AFTER transaction commits to ensure signal fires
            auto_publish = request.data.get('auto_publish', False)
            if auto_publish and trip.can_publish():
                trip.status = 'published'
                trip.full_clean()
                trip.save()
            
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
    serializer_class = BookingSerializer
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
            contact_name = request.data.get('contact_name')
            contact_phone = request.data.get('contact_phone')
            contact_email = request.data.get('contact_email')
            
            # Create booking with physical source
            booking = create_booking_atomic(
                trip_id=trip_id,
                from_stop_id=from_stop_id,
                to_stop_id=to_stop_id,
                user=request.user,
                passengers_data=passengers_data,
                payment_method='cash',
                contact_name=contact_name,
                contact_phone=contact_phone,
                contact_email=contact_email
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
        """Direct driver creation disabled - use invitation system"""
        return Response({
            'error': 'Direct driver creation is disabled',
            'message': 'Please use the invitation system to add drivers',
            'action': 'Use generate-invite endpoint'
        }, status=status.HTTP_403_FORBIDDEN)
    
    @action(detail=False, methods=['post'], url_path='generate-invite')
    def generate_invite(self, request):
        """Generate invitation code for driver (operator_admin only)"""
        if request.user.profile.role != 'operator_admin':
            return Response({'error': 'Only operator_admin can invite drivers'}, status=status.HTTP_403_FORBIDDEN)
        
        mobile = request.data.get('mobile_number')
        print(f'[GENERATE INVITE] Mobile: {mobile}')
        
        if not mobile:
            return Response({'error': 'mobile_number required'}, status=status.HTTP_400_BAD_REQUEST)
        
        if Profile.objects.filter(mobile_number=mobile).exists():
            return Response({'error': 'Mobile number already registered'}, status=status.HTTP_400_BAD_REQUEST)
        
        operator = get_operator_for_user(request.user)
        print(f'[GENERATE INVITE] Operator: {operator.id}')
        
        existing = DriverInvitation.objects.filter(
            operator=operator,
            mobile_number=mobile,
            status='pending',
            expires_at__gt=timezone.now()
        ).first()
        
        if existing:
            print(f'[GENERATE INVITE] Existing invitation found: {existing.invite_code}')
            return Response({
                'invite_code': existing.invite_code,
                'expires_at': existing.expires_at
            })
        
        from django.utils.crypto import get_random_string
        invite_code = get_random_string(8, 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789')
        expires_at = timezone.now() + timedelta(days=7)
        
        print(f'[GENERATE INVITE] Creating new invitation: {invite_code}')
        
        invitation = DriverInvitation.objects.create(
            operator=operator,
            mobile_number=mobile,
            invite_code=invite_code,
            created_by=request.user,
            expires_at=expires_at
        )
        
        print(f'[GENERATE INVITE] Success: {invite_code}')
        
        return Response({
            'invite_code': invite_code,
            'expires_at': expires_at,
            'mobile_number': mobile
        }, status=status.HTTP_201_CREATED)
    
    @action(detail=False, methods=['get'], url_path='invitations')
    def list_invitations(self, request):
        """List all invitations sent by operator"""
        operator = get_operator_for_user(request.user)
        invitations = DriverInvitation.objects.filter(operator=operator)
        
        return Response([{
            'id': inv.id,
            'mobile_number': inv.mobile_number,
            'invite_code': inv.invite_code,
            'status': inv.status,
            'created_at': inv.created_at,
            'expires_at': inv.expires_at,
            'accepted_at': inv.accepted_at
        } for inv in invitations])
    
    @action(detail=True, methods=['post'], url_path='cancel-invite')
    def cancel_invitation(self, request, pk=None):
        """Cancel pending invitation"""
        operator = get_operator_for_user(request.user)
        
        try:
            invitation = DriverInvitation.objects.get(id=pk, operator=operator, status='pending')
            invitation.status = 'cancelled'
            invitation.save()
            return Response({'message': 'Invitation cancelled'})
        except DriverInvitation.DoesNotExist:
            return Response({'error': 'Invitation not found'}, status=status.HTTP_404_NOT_FOUND)
    
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
        if request.user.profile.role != 'standalone_driver':
            return Response({
                'error': 'Only standalone drivers can request upgrade'
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
