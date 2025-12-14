"""Route-related views"""
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from datetime import timedelta

from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.decorators import action

import googlemaps
import polyline
from shapely.geometry import Point, LineString
from geopy.distance import geodesic

from ..serializers import TripsSerializer
from ..models import Trip, CityList
from ..utils.cache_keys import CacheKeys


class RouteViewSet(viewsets.ViewSet):
    api_key = ''
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def list(self, request):
        startParams = request.query_params.get('start')
        endParams = request.query_params.get('end')
        user_id = request.user.id
        
        try:
            start = CityList.objects.get(city=startParams)
            end = CityList.objects.get(city=endParams)

            cache.set(CacheKeys.route_start_city(user_id), {start.city: start.coordinates}, timeout=3600)
            cache.set(CacheKeys.route_end_city(user_id), {end.city: end.coordinates}, timeout=3600)
        except ObjectDoesNotExist:
            return Response({'message': 'you may have provided wrong start or end'}, status=status.HTTP_400_BAD_REQUEST)
        
        startCoords = start.coordinates
        endCoords = end.coordinates

        if not startCoords and not endCoords:
            return Response({'message': 'provide start and end'}, status=status.HTTP_400_BAD_REQUEST)
        
        gmaps = googlemaps.Client(key=self.api_key)
        all_routes = gmaps.directions(startCoords, endCoords, mode='driving', alternatives=True, region='ye')

        cache.set(CacheKeys.route_session(user_id), all_routes, timeout=3600)

        routes_info = [
            {'route': idx, 'summary': route['summary'], 'distance': route['legs'][0]['distance']['text']}
            for idx, route in enumerate(all_routes)
        ]
     
        return Response(routes_info, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'])
    def waypoints(self, request, pk=None):
        user_id = request.user.id
        all_routes = cache.get(CacheKeys.route_session(user_id))

        if not all_routes:
            return Response({'message': 'Route Data Expired or Not Found'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            selected_route = all_routes[int(pk)]
            route_polyline = polyline.decode(selected_route['overview_polyline']['points'])
            start_city = cache.get(CacheKeys.route_start_city(user_id))
            end_city = cache.get(CacheKeys.route_end_city(user_id))

            PROXIMITY_KM = 2.0
            cities = CityList.objects.exclude(city__in=[next(iter(start_city.items()))[0], next(iter(end_city.items()))[0]])
            matched_cities = {}
            
            for city in cities:
                best_waypoint = None
                best_distance = None
                
                for waypoint in city.waypoints:
                    coords = (waypoint['lat'], waypoint['lon'])
                    
                    if self.is_point_near_polyline(coords, route_polyline, PROXIMITY_KM):
                        nearest_point = self.find_nearest_point_on_route(coords, route_polyline)
                        if isinstance(nearest_point, Point):
                            distance_along_route = self.calculate_distance_along_route(
                                route_polyline,
                                (nearest_point.x, nearest_point.y)
                            )
                            
                            if best_distance is None or distance_along_route < best_distance:
                                best_waypoint = waypoint
                                best_distance = distance_along_route
                
                if best_waypoint is not None:
                    matched_cities[city.city] = (f"{best_waypoint['lat']}, {best_waypoint['lon']}", best_distance)
            
            close_cities = [(name, coords, dist) for name, (coords, dist) in matched_cities.items()]
            close_cities = sorted(close_cities, key=lambda x: x[2])

            cache.set(CacheKeys.route_close_cities(user_id), close_cities, timeout=3600)

            gmaps = googlemaps.Client(key=self.api_key)
            waypoints_param = [wp[1] for wp in close_cities]
            new_route = gmaps.directions(next(iter(start_city.items()))[1], next(iter(end_city.items()))[1], waypoints=waypoints_param, mode='driving', region='ye')

            cache.set(CacheKeys.route_new_route(user_id), new_route, timeout=3600)
            cache.set(CacheKeys.route_summary(user_id), selected_route['summary'], timeout=3600)

            waypoint_distances = []
            cumulative_distance = 0
            cumulative_duration = 0
            for i, leg in enumerate(new_route[0]['legs']):
                distance = leg['distance']['value']
                duration = leg['duration']['value']
                cumulative_distance += distance
                cumulative_duration += duration

                if i < len(close_cities):
                    waypoint_name = close_cities[i][0]
                else:
                    break

                waypoint_distances.append({
                    'waypoint_name': waypoint_name,
                    'cumulative_distance': f"{cumulative_distance/1000} km",
                    'cumulative_duration': f"{cumulative_duration/60} minutes"
                })

            return Response({
                'start_city': f'{next(iter(start_city.items()))[0]}',
                'end_city': f'{next(iter(end_city.items()))[0]}',
                'waypoints': waypoint_distances,
            }, status=status.HTTP_200_OK)
        
        except KeyError:
            return Response({'message': 'provide selected route'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'message': f'Error while validating the key or key not found: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)
        
    def is_point_near_polyline(self, point, polyline, threshold=1.2):
        if isinstance(point, tuple) and len(point) == 2:
            shapely_point = Point(point)
            line = LineString(polyline)
            nearest_point_on_line = line.interpolate(line.project(shapely_point))
            nearest_point_tuple = (nearest_point_on_line.x, nearest_point_on_line.y)
            return geodesic(nearest_point_tuple, point).kilometers <= threshold
        else:
            raise ValueError("Invalid point format in is_point_near_polyline")
        
    def find_nearest_point_on_route(self, point, polyline):
        if isinstance(point, tuple) and len(point) == 2:
            shapely_point = Point(point)
            line = LineString(polyline)
            return line.interpolate(line.project(shapely_point))
        else:
            raise ValueError("Invalid point format in find_nearest_point_on_route")
    
    def calculate_distance_along_route(self, polyline, point):
        if len(polyline) < 2:
            return 0
        if isinstance(point, tuple) and len(point) == 2:
            line = LineString(polyline)
            shapely_point = Point(point)
            projected_distance = line.project(shapely_point)
            if projected_distance < 1:
                return 0
            else:
                line_to_nearest_point = LineString(polyline[:int(projected_distance) + 1])
                return line_to_nearest_point.length
        else:
            raise ValueError("Invalid point format in calculate_distance_along_route")


class TripsViewSet(viewsets.ModelViewSet):
    queryset = Trip.objects.all()
    serializer_class = TripsSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        trip = serializer.save()

        user_id = request.user.id
        
        start_city = cache.get(CacheKeys.route_start_city(user_id))
        end_city = cache.get(CacheKeys.route_end_city(user_id))
        close_cities = cache.get(CacheKeys.route_close_cities(user_id))
        new_route = cache.get(CacheKeys.route_new_route(user_id))
        route_summary = cache.get(CacheKeys.route_summary(user_id))

        if not all([start_city, end_city, close_cities, new_route]):
            return Response({'message': 'Required route data not found in cache'}, status=status.HTTP_400_BAD_REQUEST)
        
        total_distance_main_trip = sum(leg['distance']['value'] for leg in new_route[0]['legs']) / 1000
        arrival_time_main_trip = timedelta(seconds=sum(leg['duration']['value'] for leg in new_route[0]['legs'])) + trip.departure_time
        
        trip.path_road = route_summary
        trip.arrival_time = arrival_time_main_trip
        trip.distance = total_distance_main_trip
        trip.save()

        price_per_km = trip.price / total_distance_main_trip

        all_stops = [next(iter(start_city.items()))[0]] + [cp[0] for cp in close_cities] + [next(iter(end_city.items()))[0]]
            
        cumulative_distances = [0]
        cumulative_durations = [0]
        for leg in new_route[0]['legs']:
            cumulative_distances.append(cumulative_distances[-1] + leg['distance']['value'] / 1000)
            cumulative_durations.append(cumulative_durations[-1] + leg['duration']['value'])

        # Note: AllTrips model reference removed - needs migration
        # Original code created AllTrips records here

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def get_queryset(self):
        return Trip.objects.filter(driver__user=self.request.user.id)


__all__ = ['RouteViewSet', 'TripsViewSet']
