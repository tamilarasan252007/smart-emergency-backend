from flask import Flask, request, jsonify
from flask_cors import CORS
import math
import requests

app = Flask(__name__)
CORS(app)

# -----------------------------
# Emergency vehicle information
# -----------------------------
emergency_vehicles = {}

# -----------------------------
# User location information
# -----------------------------
users = {}


# -----------------------------
# Calculate distance between
# two GPS coordinates
# -----------------------------
def distance_km(lat1, lon1, lat2, lon2):

    R = 6371

    lat1 = math.radians(lat1)
    lat2 = math.radians(lat2)

    dlat = lat2 - lat1
    dlon = math.radians(lon2 - lon1)

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1)
        * math.cos(lat2)
        * math.sin(dlon / 2) ** 2
    )

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


# -----------------------------
# Create demo road path
# SOURCE → ROAD → DESTINATION
# -----------------------------
def create_fallback_route():
    # Used only if OSRM cannot be reached (e.g. no internet).
    return [
        {"lat": 13.0827, "lng": 80.2707},
        {"lat": 13.0800, "lng": 80.2650},
        {"lat": 13.0780, "lng": 80.2600},
        {"lat": 13.0750, "lng": 80.2550},
        {"lat": 13.0720, "lng": 80.2500}
    ]


def geocode_place(place_name):
    # Turns a place name into (lat, lon) using OpenStreetMap's
    # Nominatim search, biased toward the greater Chennai metro
    # area using a bounding box (so nearby towns like Avadi,
    # Tambaram, etc. resolve correctly, not just the city center).
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": f"{place_name}, Tamil Nadu, India",
        "format": "json",
        "limit": 1,
        "countrycodes": "in",
        "viewbox": "76.2,13.6,80.4,8.0",  # left,top,right,bottom — covers all of Tamil Nadu
        "bounded": 1
    }
    headers = {
        "User-Agent": "SmartEmergencyTrafficSystem/1.0"
    }

    response = requests.get(url, params=params, headers=headers, timeout=5)
    results = response.json()

    if not results:
        return None

    lat = float(results[0]["lat"])
    lon = float(results[0]["lon"])
    return lat, lon

def create_route(source, destination, source_coords=None):

    if source_coords is None:
        source_coords = geocode_place(source)

    dest_coords = geocode_place(destination)

    if source_coords is None or dest_coords is None:
        print("Geocoding failed for source or destination, using fallback route")
        return create_fallback_route()

    source_lat, source_lon = source_coords
    dest_lat, dest_lon = dest_coords

    url = (
        "https://router.project-osrm.org/route/v1/driving/"
        f"{source_lon},{source_lat};{dest_lon},{dest_lat}"
        "?overview=full&geometries=geojson"
    )

    try:
        response = requests.get(url, timeout=5)
        data = response.json()

        if data.get("code") != "Ok":
            print("OSRM returned an error, using fallback route")
            return create_fallback_route()

        coordinates = data["routes"][0]["geometry"]["coordinates"]

        route = []
        for lon, lat in coordinates:
            route.append({"lat": lat, "lng": lon})

        return route

    except Exception as e:
        print("OSRM request failed, using fallback route:", e)
        return create_fallback_route()

def create_route_from_coords(source_coords, dest_coords):

    source_lat, source_lon = source_coords
    dest_lat, dest_lon = dest_coords

    url = (
        "https://router.project-osrm.org/route/v1/driving/"
        f"{source_lon},{source_lat};{dest_lon},{dest_lat}"
        "?overview=full&geometries=geojson"
    )

    try:
        response = requests.get(url, timeout=5)
        data = response.json()

        if data.get("code") != "Ok":
            print("OSRM returned an error, using fallback route")
            return create_fallback_route()

        coordinates = data["routes"][0]["geometry"]["coordinates"]

        route = []
        for lon, lat in coordinates:
            route.append({"lat": lat, "lng": lon})

        return route

    except Exception as e:
        print("OSRM request failed, using fallback route:", e)
        return create_fallback_route()
   
# -----------------------------
# Geocode a place name (used by
# the app to convert user's typed
# source/destination into lat/lng)
# -----------------------------
@app.route("/geocode", methods=["POST"])
def geocode_endpoint():

    data = request.json

    place = data.get("place")

    if not place:

        return jsonify({
            "success": False,
            "message": "place is required"
        }), 400

    coords = geocode_place(place)

    if coords is None:

        return jsonify({
            "success": False,
            "message": "Could not find location for that place"
        }), 404

    lat, lon = coords

    return jsonify({
        "success": True,
        "place": place,
        "lat": lat,
        "lng": lon
    })
@app.route("/search_places", methods=["POST"])
def search_places():

    data = request.json

    query = data.get("query")

    if not query:
        return jsonify({
            "success": True,
            "results": []
        })

    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": f"{query}, Tamil Nadu, India",
        "format": "json",
        "limit": 5,
        "countrycodes": "in",
        "viewbox": "79.9,13.25,80.35,12.85",
        "bounded": 1
    }
    headers = {
        "User-Agent": "SmartEmergencyTrafficSystem/1.0"
    }

    try:
        response = requests.get(url, params=params, headers=headers, timeout=5)
        results = response.json()

        suggestions = []
        for r in results:
            suggestions.append({
                "description": r.get("display_name"),
                "lat": float(r.get("lat")),
                "lng": float(r.get("lon"))
            })

        return jsonify({
            "success": True,
            "results": suggestions
        })

    except Exception as e:
        print("Search places failed:", e)
        return jsonify({
            "success": True,
            "results": []
        })


# -----------------------------
# User's own route endpoint
# (source -> destination for
# the app's map display only,
# separate from ambulance route)
# -----------------------------
@app.route("/user/route", methods=["POST"])
def user_route():

    data = request.json

    source = data.get("source")
    destination = data.get("destination")
    source_lat = data.get("source_lat")
    source_lng = data.get("source_lng")
    dest_lat = data.get("dest_lat")
    dest_lng = data.get("dest_lng")

    source_coords = None
    dest_coords = None

    if source_lat is not None and source_lng is not None:
        source_coords = (float(source_lat), float(source_lng))
        source_label = source or "Live location"
    else:
        if not source:
            return jsonify({
                "success": False,
                "message": "source or source_lat/source_lng is required"
            }), 400
        source_label = source

    if dest_lat is not None and dest_lng is not None:
        dest_coords = (float(dest_lat), float(dest_lng))
        destination_label = destination or "Custom destination"
    else:
        if not destination:
            return jsonify({
                "success": False,
                "message": "destination or dest_lat/dest_lng is required"
            }), 400
        destination_label = destination

    if source_coords is not None and dest_coords is not None:
        route = create_route_from_coords(source_coords, dest_coords)
    else:
        route = create_route(source_label, destination_label, source_coords=source_coords)

    return jsonify({
        "success": True,
        "source": source_label,
        "destination": destination_label,
        "route": route
    })
# -----------------------------
# Find nearest point on route
# -----------------------------
def nearest_route_index(lat, lng, route):

    nearest_index = 0
    nearest_distance = float("inf")

    for i, point in enumerate(route):

        d = distance_km(
            lat,
            lng,
            point["lat"],
            point["lng"]
        )

        if d < nearest_distance:
            nearest_distance = d
            nearest_index = i

    return nearest_index, nearest_distance


# -----------------------------
# Check whether user is
# travelling on emergency path
# -----------------------------
def user_on_route(lat, lng, route):

    index, distance = nearest_route_index(
        lat,
        lng,
        route
    )

    # User is considered on the road path
    # if within 500 meters.

    if distance <= 0.5:
        return True, index, distance

    return False, index, distance


# -----------------------------
# Check whether user is
# ahead of ambulance
# -----------------------------
def user_is_ahead(user_index, ambulance_index):
    return user_index >= ambulance_index
# -----------------------------
# Emergency vehicle endpoint
# -----------------------------
@app.route("/emergency", methods=["POST"])
def receive_emergency():

    global emergency_vehicles

    data = request.json

    vehicle_id = data.get("vehicle_id")
    source = data.get("source")
    destination = data.get("destination")
    level = data.get("level", "CRITICAL")

    source_lat = data.get("source_lat")
    source_lng = data.get("source_lng")
    dest_lat = data.get("dest_lat")
    dest_lng = data.get("dest_lng")

    if not vehicle_id:
        return jsonify({
            "success": False,
            "message": "vehicle_id is required"
        }), 400

    source_coords = None
    dest_coords = None

    if source_lat is not None and source_lng is not None:
        source_coords = (float(source_lat), float(source_lng))
        source = source or "Custom source"

    if dest_lat is not None and dest_lng is not None:
        dest_coords = (float(dest_lat), float(dest_lng))
        destination = destination or "Custom destination"

    if source_coords is None and not source:
        return jsonify({
            "success": False,
            "message": "source or source_lat/source_lng is required"
        }), 400

    if dest_coords is None and not destination:
        return jsonify({
            "success": False,
            "message": "destination or dest_lat/dest_lng is required"
        }), 400

    if source_coords is not None and dest_coords is not None:
        route = create_route_from_coords(source_coords, dest_coords)
    else:
        route = create_route(source, destination, source_coords=source_coords)

    emergency_vehicles[vehicle_id] = {

        "vehicle_id": vehicle_id,

        "source": source,

        "destination": destination,

        "level": level,

        "active": True,

        "location": route[0],

        "route": route
    }

    return jsonify({

        "success": True,

        "message": "Emergency vehicle received",

        "emergency": emergency_vehicles[vehicle_id]
    })

# -----------------------------
# Update ambulance location
# -----------------------------
@app.route("/emergency/location", methods=["POST"])
def update_emergency_location():

    global emergency_vehicles

    data = request.json

    vehicle_id = data.get("vehicle_id")
    lat = data.get("lat")
    lng = data.get("lng")

    if not vehicle_id:
        return jsonify({
            "success": False,
            "message": "vehicle_id is required"
        }), 400

    if vehicle_id not in emergency_vehicles:
        return jsonify({
            "success": False,
            "message": "No active emergency vehicle with that vehicle_id"
        }), 404

    if lat is None or lng is None:

        return jsonify({
            "success": False,
            "message": "lat and lng are required"
        }), 400

    emergency_vehicles[vehicle_id]["location"] = {

        "lat": lat,

        "lng": lng
    }

    return jsonify({

        "success": True,

        "location": emergency_vehicles[vehicle_id]["location"]
    })


# -----------------------------
# Check user location
# -----------------------------
@app.route("/user/location", methods=["POST"])
def update_user_location():

    data = request.json

    user_id = data.get("user_id")
    lat = data.get("lat")
    lng = data.get("lng")

    if user_id is None or lat is None or lng is None:

        return jsonify({

            "success": False,

            "message": "user_id, lat and lng are required"

        }), 400

    users[user_id] = {

        "lat": lat,

        "lng": lng
    }

    result = check_user_for_alert(
        user_id,
        lat,
        lng
    )

    return jsonify(result)


# -----------------------------
# Alert decision
# -----------------------------
def check_user_for_alert(user_id, lat, lng):

    if not emergency_vehicles:

        return {

            "success": True,

            "alert": False,

            "reason": "No active emergency vehicle"
        }

    WARNING_DISTANCE_KM = 5
    best_alert = None
    best_distance = None
    closest_reason = "No active emergency vehicle"
    closest_distance_from_route = None

    for vehicle_id, vehicle in emergency_vehicles.items():

        if not vehicle["active"]:
            continue

        route = vehicle["route"]

        ambulance_lat = vehicle["location"]["lat"]
        ambulance_lng = vehicle["location"]["lng"]

        on_route, user_index, road_distance = user_on_route(lat, lng, route)

        if not on_route:
            if closest_distance_from_route is None or road_distance < closest_distance_from_route:
                closest_distance_from_route = road_distance
                closest_reason = "User is not on emergency vehicle path"
            continue

        ambulance_index, ambulance_route_distance = nearest_route_index(
            ambulance_lat, ambulance_lng, route
        )

               distance_to_ambulance = distance_km(lat, lng, ambulance_lat, ambulance_lng)

        ahead = user_is_ahead(user_index, ambulance_index)
        very_close = distance_to_ambulance <= 1.0  # within 1km overrides index ordering

        if not ahead and not very_close:
            closest_reason = "User is behind emergency vehicle"
            continue

        if distance_to_ambulance > WARNING_DISTANCE_KM:
            closest_reason = "User is too far from emergency vehicle"
            continue

        # This vehicle qualifies for an alert — keep the closest one if multiple do.
        if best_distance is None or distance_to_ambulance < best_distance:
            best_distance = distance_to_ambulance
            best_alert = {
                "success": True,
                "alert": True,
                "reason": "Emergency vehicle is approaching on your path",
                "user_id": user_id,
                "distance_km": round(distance_to_ambulance, 3),
                "emergency": {
                    "vehicle_id": vehicle["vehicle_id"],
                    "source": vehicle["source"],
                    "destination": vehicle["destination"],
                    "level": vehicle["level"]
                },
                "message": "Emergency vehicle approaching. Please give way."
            }

    if best_alert is not None:
        return best_alert

    result = {
        "success": True,
        "alert": False,
        "reason": closest_reason
    }

    if closest_distance_from_route is not None:
        result["distance_from_route_km"] = round(closest_distance_from_route, 3)

    return result


# -----------------------------
# Get current emergency
# -----------------------------
@app.route("/emergency", methods=["GET"])
def get_emergency():

    return jsonify({

        "success": True,

        "emergencies": list(emergency_vehicles.values())
    })

# -----------------------------
# Stop emergency
# -----------------------------
@app.route("/emergency/stop", methods=["POST"])
def stop_emergency():

    global emergency_vehicles

    data = request.json or {}
    vehicle_id = data.get("vehicle_id")

    if vehicle_id:
        if vehicle_id in emergency_vehicles:
            emergency_vehicles[vehicle_id]["active"] = False
            return jsonify({
                "success": True,
                "message": f"Emergency vehicle {vehicle_id} stopped"
            })
        else:
            return jsonify({
                "success": False,
                "message": "No active emergency vehicle with that vehicle_id"
            }), 404
    else:
        # No vehicle_id given — stop all active emergencies (backward-compatible testing convenience).
        for v in emergency_vehicles.values():
            v["active"] = False
        return jsonify({
            "success": True,
            "message": "All emergency vehicles stopped"
        })

# -----------------------------
# Home page
# -----------------------------
@app.route("/", methods=["GET"])
def home():

    return jsonify({

        "system": "Smart Emergency Traffic Priority System",

        "status": "Backend running",

                  "endpoints": [

            "POST /emergency",

            "POST /emergency/location",

            "POST /user/location",

            "GET /emergency",

            "POST /emergency/stop",

            "POST /geocode",

            "POST /user/route"
        ]
        
    })


# -----------------------------
# Start server
# -----------------------------
if __name__ == "__main__":

    import os
    port = int(os.environ.get("PORT", 5000))

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
