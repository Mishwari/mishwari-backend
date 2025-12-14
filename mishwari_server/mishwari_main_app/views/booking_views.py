"""Booking-related views using BookingService"""
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.conf import settings
from django.db import transaction

from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError

import stripe

from ..serializers import BookingSerializer, BookingTripSerializer, PassengerSerializer
from ..models import Booking, Passenger, Driver
from ..services import BookingService
from ..services.booking_service import BookingAlreadyCancelledError
from ..payment_gateways.stripe_payment_gateway import StripePaymentGateway
from ..payment_gateways.wallet_payment_gateway import WalletPaymentGateway


class BookingViewSet(viewsets.ModelViewSet):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = BookingSerializer

    def get_queryset(self):
        from ..utils.operator_utils import get_operator_for_user
        
        user = self.request.user
        profile = user.profile
        
        if profile.role == 'passenger':
            return Booking.objects.filter(user=user)
        
        elif profile.role in ['standalone_driver', 'invited_driver']:
            try:
                driver = Driver.objects.get(user=user)
                return Booking.objects.filter(trip__driver=driver) | Booking.objects.filter(trip__actual_driver=driver)
            except Driver.DoesNotExist:
                return Booking.objects.none()
        
        elif profile.role == 'operator_admin':
            operator = get_operator_for_user(user)
            return Booking.objects.filter(trip__operator=operator)
        
        return Booking.objects.none()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        payment_method = request.data.get('payment_method', 'stripe')
        gateway = None

        if payment_method == 'stripe':
            gateway = StripePaymentGateway()
        elif payment_method == 'wallet':
            gateway = WalletPaymentGateway()
        elif payment_method == 'cash':
            gateway = None
        else:
            raise ValidationError('Unsupported payment method')

        try:
            with transaction.atomic():
                booking_data = serializer.validated_data
                booking_data['user'] = request.user

                booking = serializer.save(user=request.user)
                booking_details = {
                    'user': booking_data['user'],
                    'trip': booking_data['trip'],
                    'amount': booking_data.get('total_fare', 0),
                    'booking_id': booking.id
                }

                booking.booking_source = 'platform'
                booking.created_by = request.user
                booking.save()
                
                if payment_method == 'stripe':
                    payment_url = gateway.initiate_payment(booking_details)
                    headers = self.get_success_headers(serializer.data)
                    return Response({'payment_url': payment_url, 'booking_id': booking.id}, status=status.HTTP_202_ACCEPTED, headers=headers)
                elif payment_method == 'wallet':
                    gateway.initiate_payment(booking_details)
                    booking.status = 'active'
                    booking.is_paid = True
                    booking.payment_method = 'wallet'
                    booking.save()
                    return Response({'message': 'Payment successful using wallet', 'booking': serializer.data}, status=status.HTTP_200_OK)
                elif payment_method == 'cash':
                    booking.status = 'pending'
                    booking.save()
                    headers = self.get_success_headers(serializer.data)
                    return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
                else:
                    headers = self.get_success_headers(serializer.data)
                    return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
        except ValidationError as e:
            raise e
        except Exception as e:
            return Response({'error': 'An unexpected error occurred'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['post'], url_path='cancel')
    def cancel_booking(self, request, pk=None):
        from ..utils.operator_utils import get_operator_for_user
        
        booking = self.get_object()
        user = request.user
        profile = user.profile
        
        has_permission = False
        
        if booking.user == user:
            has_permission = True
        elif profile.role == 'operator_admin':
            operator = get_operator_for_user(user)
            if booking.trip.operator == operator:
                has_permission = True
        elif profile.role in ['standalone_driver', 'invited_driver']:
            try:
                driver = Driver.objects.get(user=user)
                if booking.trip.driver == driver:
                    has_permission = True
            except Driver.DoesNotExist:
                pass
        
        if not has_permission:
            return Response(
                {'error': 'You do not have permission to cancel this booking'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        try:
            BookingService().cancel_booking(booking.id)
            return Response({'message': 'Booking cancelled successfully'}, status=status.HTTP_200_OK)
        except BookingAlreadyCancelledError:
            return Response({'error': 'Booking already cancelled'}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], url_path='complete')
    def complete_booking(self, request, pk=None):
        booking = self.get_object()
        
        profile = request.user.profile
        if profile.role not in ['standalone_driver', 'invited_driver', 'operator_admin']:
            return Response({'error': 'Only drivers/operators can complete bookings'}, 
                          status=status.HTTP_403_FORBIDDEN)
        
        if profile.role in ['standalone_driver', 'invited_driver']:
            driver = Driver.objects.get(user=request.user)
            if booking.trip.driver != driver:
                return Response({'error': 'Not your trip'}, 
                              status=status.HTTP_403_FORBIDDEN)
        
        booking.status = 'completed'
        booking.save()
        
        serializer = self.get_serializer(booking)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='confirm')
    def confirm_booking(self, request, pk=None):
        from ..utils.operator_utils import get_operator_for_user
        
        booking = self.get_object()
        
        profile = request.user.profile
        if profile.role not in ['standalone_driver', 'invited_driver', 'operator_admin']:
            return Response({'error': 'Only drivers/operators can confirm bookings'}, 
                          status=status.HTTP_403_FORBIDDEN)
        
        if profile.role in ['standalone_driver', 'invited_driver']:
            driver = Driver.objects.get(user=request.user)
            if booking.trip.driver != driver and booking.trip.actual_driver != driver:
                return Response({'error': 'Not your trip'}, 
                              status=status.HTTP_403_FORBIDDEN)
        elif profile.role == 'operator_admin':
            operator = get_operator_for_user(request.user)
            if booking.trip.operator != operator:
                return Response({'error': 'Not your trip'}, 
                              status=status.HTTP_403_FORBIDDEN)
        
        if booking.status != 'pending':
            return Response({'error': 'Only pending bookings can be confirmed'}, 
                          status=status.HTTP_400_BAD_REQUEST)
        
        booking.status = 'confirmed'
        booking.save()
        
        serializer = self.get_serializer(booking)
        return Response(serializer.data, status=status.HTTP_200_OK)


class BookingTripsViewSet(viewsets.ModelViewSet):
    queryset = Booking.objects.all()
    serializer_class = BookingTripSerializer


class PassengersViewSet(viewsets.ModelViewSet):
    serializer_class = PassengerSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def get_queryset(self):
        return Passenger.objects.filter(user=self.request.user.id)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def update(self, request, *args, **kwargs):
        passenger = self.get_object()
        if passenger.user != request.user:
            return Response(
                {'error': 'You do not have permission to update this passenger'},
                status=status.HTTP_403_FORBIDDEN
            )
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        passenger = self.get_object()
        if passenger.user != request.user:
            return Response(
                {'error': 'You do not have permission to update this passenger'},
                status=status.HTTP_403_FORBIDDEN
            )
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        passenger = self.get_object()
        if passenger.user != request.user:
            return Response(
                {'error': 'You do not have permission to delete this passenger'},
                status=status.HTTP_403_FORBIDDEN
            )
        return super().destroy(request, *args, **kwargs)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        data = serializer.data
        
        user_profile = request.user.profile
        for passenger in data:
            if passenger.get('name') == user_profile.full_name:
                passenger['is_checked'] = True
        
        return Response(data)

    @action(detail=False, methods=['post'], url_path='bulk-update-checked')
    def bulk_update_checked(self, request):
        passengers_data = request.data.get('passengers', [])
        
        for passenger_data in passengers_data:
            passenger_id = passenger_data.get('id')
            is_checked = passenger_data.get('is_checked', False)
            
            if passenger_id:
                try:
                    passenger = Passenger.objects.get(id=passenger_id, user=request.user)
                    passenger.is_checked = is_checked
                    passenger.save()
                except Passenger.DoesNotExist:
                    pass
        
        return Response({'message': 'Passengers updated successfully'}, status=status.HTTP_200_OK)


@csrf_exempt
def stripe_webhook(request):
    payload = request.body
    sig_header = request.META['HTTP_STRIPE_SIGNATURE']
    endpoint_secret = settings.STRIPE_WEBHOOK_SECRET

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, endpoint_secret
        )
    except ValueError as e:
        return JsonResponse({'error': str(e)}, status=400)
    except stripe.error.SignatureVerificationError as e:
        return JsonResponse({'error': str(e)}, status=400)

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        handle_successful_payment(session)

    return JsonResponse({'status': 'success'}, status=200)


def handle_successful_payment(session):
    try:
        booking_id = session['metadata']['booking_id']
        booking = Booking.objects.get(id=int(booking_id))
        booking.is_paid = True
        booking.status = 'active'
        booking.save()
    except Booking.DoesNotExist:
        pass


__all__ = [
    'BookingViewSet',
    'BookingTripsViewSet',
    'PassengersViewSet',
    'stripe_webhook',
    'handle_successful_payment',
]
