import googlemaps
from geopy.distance import distance

def get_routes(api_key, start, end):
    gmaps = googlemaps.Client(key=api_key)
    directions_result = gmaps.directions(start, end, mode='driving', alternatives=True)
    return directions_result

def is_close_to_route(point, route, threshold=0.2):
    for leg in route['legs']:
        for step in leg['steps']:
            start_step = (step['start_location']['lat'], step['start_location']['lng'])
            end_step = (step['end_location']['lat'], step['end_location']['lng'])
            if distance(point, start_step).km <= threshold or distance(point, end_step).km <= threshold:
                return True
    return False

# Replace with your actual API key
api_key = ''
start = '12.791077, 45.017897' #mukalla 
end = '15.949157, 48.810048'  #
all_routes = get_routes(api_key, start, end)

# Print summary of each route
for idx, route in enumerate(all_routes):
    print(f"Route {idx + 1}: {route['summary']}, Distance: {route['legs'][0]['distance']['text']}")

# User selects a route
route_number = int(input("Enter the number of the route you want to select: "))
selected_route = all_routes[route_number - 1]

# Example waypoints (replace with actual waypoints)
waypoints = [(15.267748, 48.613757)]  # Replace with real coordinates

# Check which waypoints are close to the selected route
close_waypoints = [wp for wp in waypoints if is_close_to_route(wp, selected_route)]
print("Waypoints close to the route:", close_waypoints)
