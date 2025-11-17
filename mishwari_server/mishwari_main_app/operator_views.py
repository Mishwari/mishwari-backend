from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError

from .models import Bus, Trip, Booking, Driver, TripStop, Passenger, BookingPassenger, Seat, BusOperator, UpgradeRequest, CityList
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
import polyline


class OperatorFleetViewSet(viewsets.ModelViewSet):
    """Operator fleet management"""
    serializer_class = BusSerializer
    permission_classes = [IsAuthenticated, IsOperatorOrAdmin]
    authentication_classes = [JWTAuthentication]
    
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
        # For role='driver': Get operator via Driver record
        # For role='operator_admin': Get operator via profile
        print(f'[FLEET QUERYSET] User: {self.request.user.username}, Role: {self.request.user.profile.role}')
        try:
            driver = Driver.objects.get(user=self.request.user)
            print(f'[FLEET QUERYSET] Found Driver ID: {driver.id}, Operator ID: {driver.operator.id}')
            buses = Bus.objects.filter(operator=driver.operator)
            print(f'[FLEET QUERYSET] Found {buses.count()} buses')
            return buses
        except Driver.DoesNotExist:
            # operator_admin case: find operator by profile
            profile = self.request.user.profile
            print(f'[FLEET QUERYSET] No Driver found, searching BusOperator by mobile: {profile.mobile_number}')
            operators = BusOperator.objects.filter(contact_info=profile.mobile_number)
            if operators.exists():
                print(f'[FLEET QUERYSET] Found BusOperator ID: {operators.first().id}')
                buses = Bus.objects.filter(operator=operators.first())
                print(f'[FLEET QUERYSET] Found {buses.count()} buses')
                return buses
            print(f'[FLEET QUERYSET] No BusOperator found! Returning empty queryset')
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
            queryset = Trip.objects.filter(operator=driver.operator)
        except Driver.DoesNotExist:
            # operator_admin case: find operator by profile
            profile = self.request.user.profile
            print(f'[TRIPS QUERYSET] No Driver found, searching BusOperator by mobile: {profile.mobile_number}')
            operators = BusOperator.objects.filter(contact_info=profile.mobile_number)
            if operators.exists():
                print(f'[TRIPS QUERYSET] Found BusOperator ID: {operators.first().id}')
                queryset = Trip.objects.filter(operator=operators.first())
            else:
                print(f'[TRIPS QUERYSET] No BusOperator found! Returning empty queryset')
                return Trip.objects.none()
        
        # Filter by status if provided
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        return queryset
    
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
            
            driver = Driver.objects.get(user=request.user)
            bus = Bus.objects.get(id=request.data['bus'], operator=driver.operator)
            
            trip = create_trip_from_cached_route(
                operator=driver.operator,
                bus=bus,
                driver=driver,
                cached_data=cached_data,
                selected_route=selected_route,
                trip_data=request.data,
                selected_waypoint_ids=request.data.get('selected_waypoints', []),
                custom_prices=request.data.get('custom_prices', {})
            )
            
            clear_route_session(session_id)
            
            serializer = self.get_serializer(trip)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
            
        except Driver.DoesNotExist:
            return Response({'error': 'Driver not found'}, status=status.HTTP_404_NOT_FOUND)
        except Bus.DoesNotExist:
            return Response({'error': 'Bus not found or not owned by operator'}, status=status.HTTP_404_NOT_FOUND)
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
            print(f'[DRIVER MGMT QUERYSET] Found Driver ID: {driver.id}, Operator ID: {driver.operator.id}')
            return Driver.objects.filter(operator=driver.operator)
        except Driver.DoesNotExist:
            profile = self.request.user.profile
            print(f'[DRIVER MGMT QUERYSET] Profile ID: {profile.id}, Role: {profile.role}')
            operator = BusOperator.objects.filter(contact_info=profile.mobile_number).first()
            print(f'[DRIVER MGMT QUERYSET] Operator ID: {operator.id}')
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
