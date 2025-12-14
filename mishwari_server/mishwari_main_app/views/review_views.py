"""Review-related views"""
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication

from ..serializers import TripReviewSerializer
from ..models import TripReview, Booking


class TripReviewViewSet(viewsets.ModelViewSet):
    serializer_class = TripReviewSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    
    def get_queryset(self):
        return TripReview.objects.filter(booking__user=self.request.user)
    
    def create(self, request):
        booking_id = request.data.get('booking')
        
        try:
            booking = Booking.objects.get(id=booking_id, user=request.user)
        except Booking.DoesNotExist:
            return Response({'error': 'Booking not found'}, 
                          status=status.HTTP_404_NOT_FOUND)
        
        if booking.status != 'completed':
            return Response({'error': 'Can only review completed trips'}, 
                          status=status.HTTP_400_BAD_REQUEST)
        
        if hasattr(booking, 'review'):
            return Response({'error': 'Booking already reviewed'}, 
                          status=status.HTTP_400_BAD_REQUEST)
        
        trip = booking.trip
        resources = trip.get_resources()
        
        review = TripReview.objects.create(
            booking=booking,
            bus_snapshot=resources['bus'],
            driver_snapshot=resources['driver'],
            operator_snapshot=trip.operator,
            overall_rating=request.data['overall_rating'],
            bus_condition_rating=request.data['bus_condition_rating'],
            driver_rating=request.data['driver_rating'],
            comment=request.data.get('comment', '')
        )
        
        serializer = self.get_serializer(review)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


__all__ = ['TripReviewViewSet']
