import googlemaps
import polyline
from geopy.distance import geodesic
from shapely.geometry import Point, LineString

def get_routes(api_key, start, end):
    gmaps = googlemaps.Client(key=api_key)
    directions_result = gmaps.directions(start, end, mode='driving', alternatives=True)
    return directions_result

def is_point_near_polyline(point, polyline, threshold=1.2):
    line = LineString(polyline)
    shapely_point = Point(point)
    nearest_point_on_line = line.interpolate(line.project(shapely_point))
    
    nearest_point_tuple = (nearest_point_on_line.x, nearest_point_on_line.y)
    
    return geodesic(nearest_point_tuple, point).kilometers <= threshold

api_key = ''
start = '12.791077,45.017897'
end = '15.949157, 48.810048'
all_routes = get_routes(api_key, start, end)

for idx, route in enumerate(all_routes):
    print(f"Route {idx + 1}: {route['summary']}, Distance: {route['legs'][0]['distance']['text']}")
route_number = int(input("Enter the number of the route you want to select: "))
selected_route = all_routes[route_number - 1]

route_polyline = polyline.decode(selected_route['overview_polyline']['points'])

waypoints = [(15.475873, 45.459673),(15.499686, 45.451547),(16.012282, 47.424470),(13.803443, 47.564834),(13.302453, 45.582071)]  # Replace with real coordinates

close_waypoints = [wp for wp in waypoints if is_point_near_polyline(wp, route_polyline)]
print("Waypoints close to the route:", close_waypoints)
