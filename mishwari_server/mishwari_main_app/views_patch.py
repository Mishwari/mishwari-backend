# Patch for TripSearchView - replace in views.py

class TripSearchView(viewsets.ViewSet):
    """Search trips by from/to cities and date"""
    
    def list(self, request):
        # Support both old (pickup/destination) and new (from_city/to_city) parameters
        from_city = self.request.query_params.get('pickup') or self.request.query_params.get('from_city')
        to_city = self.request.query_params.get('destination') or self.request.query_params.get('to_city')
        date_str = self.request.query_params.get('date', None)

        if from_city and to_city and date_str:
            from datetime import datetime
            try:
                filter_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                trips = Trip.objects.filter(
                    from_city__city=from_city,
                    to_city__city=to_city,
                    journey_date=filter_date,
                    status='scheduled'
                ).select_related('from_city', 'to_city', 'bus', 'driver')
                
                serializer = TripsSerializer(trips, many=True)
                return Response(serializer.data)
            except ValueError:
                return Response({'error': 'Invalid date format'}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response({'error': 'pickup/destination (or from_city/to_city) and date are required'}, status=status.HTTP_400_BAD_REQUEST)
    
    def retrieve(self, request, pk=None):
        trip = get_object_or_404(Trip.objects.all(), pk=pk)
        serializer = TripsSerializer(trip)
        return Response(serializer.data)
    
    def get_permissions(self):
        if self.request.method in ['GET']:
            return [AllowAny()]
        return [IsAdminUser()]
