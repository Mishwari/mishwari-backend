import uuid
import googlemaps
import polyline
from shapely.geometry import Point, LineString
from geopy.distance import geodesic
from django.conf import settings
from django.core.cache import cache
from .models import CityList


def get_google_maps_client():
    api_key = getattr(settings, 'GOOGLE_MAPS_API_KEY', None)
    if not api_key or api_key == '':
        raise ValueError("GOOGLE_MAPS_API_KEY not configured in settings")
    return googlemaps.Client(key=api_key)


def cache_route_session(from_city, to_city, routes_data):
    """Cache full route data with session ID. Returns: session_id (UUID)"""
    session_id = str(uuid.uuid4())
    cache_key = f'route_session_{session_id}'
    
    cache.set(cache_key, {
        'from_city': {
            'id': from_city.id,
            'name': from_city.city,
            'coords': f"{from_city.latitude},{from_city.longitude}"
        },
        'to_city': {
            'id': to_city.id,
            'name': to_city.city,
            'coords': f"{to_city.latitude},{to_city.longitude}"
        },
        'routes': routes_data
    }, timeout=3600)
    
    return session_id


def get_cached_route_session(session_id):
    """Retrieve cached route data by session ID"""
    cache_key = f'route_session_{session_id}'
    return cache.get(cache_key)


def clear_route_session(session_id):
    """Clear cached route data after trip creation"""
    cache_key = f'route_session_{session_id}'
    cache.delete(cache_key)


def detect_waypoints_from_polyline(polyline_points, from_city, to_city):
    """Detect cities along route polyline. Returns: [{city_id, city_name, distance_from_start_km}]"""
    PROXIMITY_KM = 2.0
    cities = CityList.objects.exclude(id__in=[from_city.id, to_city.id])
    matched_cities = {}
    
    for city in cities:
        best_distance = None
        
        for waypoint in city.waypoints:
            point = (float(waypoint['lat']), float(waypoint['lon']))
            if is_point_near_polyline(point, polyline_points, PROXIMITY_KM):
                distance = calculate_distance_along_route(polyline_points, point)
                
                # Keep earliest waypoint on route for this city
                if best_distance is None or distance < best_distance:
                    best_distance = distance
                    matched_cities[city.id] = {
                        'city_id': city.id,
                        'city_name': city.city,
                        'distance_from_start_km': distance
                    }
    
    waypoints = list(matched_cities.values())
    waypoints.sort(key=lambda x: x['distance_from_start_km'])
    return waypoints


def is_point_near_polyline(point, polyline_points, threshold=1.2):
    """Check if point is within threshold km of polyline"""
    shapely_point = Point(point[1], point[0])  # Point(lon, lat)
    line = LineString([(p[1], p[0]) for p in polyline_points])  # LineString expects (lon, lat)
    nearest = line.interpolate(line.project(shapely_point))
    nearest_tuple = (nearest.y, nearest.x)  # Convert back to (lat, lon) for geodesic
    return geodesic(nearest_tuple, point).kilometers <= threshold


def calculate_distance_along_route(polyline_points, point):
    """Calculate distance along route to point in km"""
    if len(polyline_points) < 2:
        return 0
    
    line = LineString([(p[1], p[0]) for p in polyline_points])
    shapely_point = Point(point[1], point[0])
    
    # Find the projection distance along the line (in the line's units)
    projection_distance = line.project(shapely_point)
    
    # Calculate actual distance in km by walking the polyline
    cumulative_distance = 0
    cumulative_line_distance = 0
    
    for i in range(len(polyline_points) - 1):
        p1 = polyline_points[i]
        p2 = polyline_points[i + 1]
        
        # Calculate segment length in both coordinate units and km
        segment_line = LineString([(p1[1], p1[0]), (p2[1], p2[0])])
        segment_line_length = segment_line.length
        segment_km = geodesic(p1, p2).kilometers
        
        # Check if projection falls within this segment
        if cumulative_line_distance + segment_line_length >= projection_distance:
            # Interpolate within this segment
            ratio = (projection_distance - cumulative_line_distance) / segment_line_length if segment_line_length > 0 else 0
            cumulative_distance += segment_km * ratio
            return cumulative_distance
        
        cumulative_distance += segment_km
        cumulative_line_distance += segment_line_length
    
    return cumulative_distance
