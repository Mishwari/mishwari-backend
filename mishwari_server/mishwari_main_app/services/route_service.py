"""Route planning service using Google Maps"""
import googlemaps
import polyline
from shapely.geometry import Point, LineString
from geopy.distance import geodesic
from django.core.cache import cache
from ..models import CityList
from ..utils.cache_keys import CacheKeys


class RouteService:
    def __init__(self, api_key=''):
        self.api_key = api_key
        self.gmaps = googlemaps.Client(key=api_key) if api_key else None
    
    def get_routes(self, user_id, start_city_name, end_city_name):
        """Get all available routes between two cities"""
        start = CityList.objects.get(city=start_city_name)
        end = CityList.objects.get(city=end_city_name)
        
        cache.set(CacheKeys.route_start_city(user_id), {start.city: start.coordinates}, timeout=3600)
        cache.set(CacheKeys.route_end_city(user_id), {end.city: end.coordinates}, timeout=3600)
        
        all_routes = self.gmaps.directions(start.coordinates, end.coordinates, mode='driving', alternatives=True, region='ye')
        cache.set(CacheKeys.route_session(user_id), all_routes, timeout=3600)
        
        return [{
            'route': idx,
            'summary': route['summary'],
            'distance': route['legs'][0]['distance']['text']
        } for idx, route in enumerate(all_routes)]
    
    def get_waypoints_for_route(self, user_id, route_index):
        """Get waypoints for a selected route"""
        all_routes = cache.get(CacheKeys.route_session(user_id))
        if not all_routes:
            raise ValueError('Route data expired or not found')
        
        selected_route = all_routes[int(route_index)]
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
                
                if self._is_point_near_polyline(coords, route_polyline, PROXIMITY_KM):
                    nearest_point = self._find_nearest_point_on_route(coords, route_polyline)
                    if isinstance(nearest_point, Point):
                        distance_along_route = self._calculate_distance_along_route(
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
        
        waypoints_param = [wp[1] for wp in close_cities]
        new_route = self.gmaps.directions(
            next(iter(start_city.items()))[1],
            next(iter(end_city.items()))[1],
            waypoints=waypoints_param,
            mode='driving',
            region='ye'
        )
        
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
        
        return {
            'start_city': next(iter(start_city.items()))[0],
            'end_city': next(iter(end_city.items()))[0],
            'waypoints': waypoint_distances,
        }
    
    def _is_point_near_polyline(self, point, polyline, threshold=1.2):
        if isinstance(point, tuple) and len(point) == 2:
            shapely_point = Point(point)
            line = LineString(polyline)
            nearest_point_on_line = line.interpolate(line.project(shapely_point))
            nearest_point_tuple = (nearest_point_on_line.x, nearest_point_on_line.y)
            return geodesic(nearest_point_tuple, point).kilometers <= threshold
        else:
            raise ValueError("Invalid point format")
    
    def _find_nearest_point_on_route(self, point, polyline):
        if isinstance(point, tuple) and len(point) == 2:
            shapely_point = Point(point)
            line = LineString(polyline)
            return line.interpolate(line.project(shapely_point))
        else:
            raise ValueError("Invalid point format")
    
    def _calculate_distance_along_route(self, polyline, point):
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
            raise ValueError("Invalid point format")
