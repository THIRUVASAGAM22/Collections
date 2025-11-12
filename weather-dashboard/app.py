import os
import requests
import datetime
from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_sqlalchemy import SQLAlchemy

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# --- Database Configuration ---
# Configure SQLite database path (creates 'weather.db' in the project root)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///weather.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- Database Model Definition ---
# Model for storing favorite cities
class FavoriteCity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    city_name = db.Column(db.String(100), unique=True, nullable=False)

    def __repr__(self):
        return f'<FavoriteCity {self.city_name}>'

# --- API Keys and URLs ---
OPENWEATHERMAP_API_KEY = os.getenv("OPENWEATHERMAP_API_KEY")
CURRENT_WEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"
FORECAST_URL = "https://api.openweathermap.org/data/2.5/forecast"

# --- Helper Functions for API Calls ---

def get_weather_data(city_name):
    """Fetches current weather data for a given city."""
    params = {
        'q': city_name,
        'appid': OPENWEATHERMAP_API_KEY,
        'units': 'metric'
    }
    try:
        response = requests.get(CURRENT_WEATHER_URL, params=params)
        response.raise_for_status()
        weather_data = response.json()

        if weather_data.get('cod') == 200:
            data = {
                'city': weather_data['name'],
                'country': weather_data['sys']['country'],
                'temperature': round(weather_data['main']['temp']),
                'description': weather_data['weather'][0]['description'].capitalize(),
                'icon': weather_data['weather'][0]['icon'],
                'humidity': weather_data['main']['humidity'],
                'wind_speed': weather_data['wind']['speed'],
            }
            return data
        else:
            return {"error": weather_data.get('message', 'City not found or invalid response.')}

    except requests.exceptions.RequestException as e:
        print(f"API Request Error: {e}")
        return {"error": "Could not connect to the weather service."}
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return {"error": "An internal server error occurred."}


def get_forecast_data(city_name):
    """Fetches 5-day / 3-hour forecast data for a given city."""
    params = {
        'q': city_name,
        'appid': OPENWEATHERMAP_API_KEY,
        'units': 'metric'
    }
    try:
        response = requests.get(FORECAST_URL, params=params)
        response.raise_for_status()
        forecast_data = response.json()

        if forecast_data.get('cod') == '200':
            daily_forecast = {}
            for item in forecast_data['list']:
                timestamp = datetime.datetime.fromtimestamp(item['dt'])
                day = timestamp.strftime('%Y-%m-%d')
                day_name = timestamp.strftime('%a') 
                
                if day not in daily_forecast:
                    daily_forecast[day] = {
                        'name': day_name,
                        'temperatures': [],
                        'icons': [],
                        'descriptions': []
                    }
                
                daily_forecast[day]['temperatures'].append(item['main']['temp'])
                daily_forecast[day]['icons'].append(item['weather'][0]['icon'])
                daily_forecast[day]['descriptions'].append(item['weather'][0]['description'])
            
            processed_forecast = []
            unique_days = list(daily_forecast.keys())
            
            for i in range(len(unique_days)):
                day_key = unique_days[i]
                day_data = daily_forecast[day_key]
                
                if len(processed_forecast) >= 5:
                    break
                
                temps = day_data['temperatures']
                # Use the mid-day entry (e.g., 12:00 or 15:00) as the representative icon/description
                representative_index = min(3, len(temps) - 1)
                
                processed_forecast.append({
                    'day': day_data['name'],
                    'date': day_key,
                    'temp_min': round(min(temps)),
                    'temp_max': round(max(temps)),
                    'icon': day_data['icons'][representative_index],
                    'description': day_data['descriptions'][representative_index].capitalize()
                })
            
            return processed_forecast
        
        else:
            return {"error": forecast_data.get('message', 'Forecast data not available.')}

    except requests.exceptions.RequestException:
        return {"error": "Could not connect to the weather service for forecast."}
    except Exception as e:
        print(f"Forecast processing error: {e}")
        return {"error": "An internal server error occurred during forecast processing."}


# --- Routes ---

@app.route('/')
def index():
    """Renders the main dashboard page and fetches all saved favorites."""
    favorite_cities = FavoriteCity.query.all()
    
    return render_template(
        'index.html', 
        default_city="Tamilnadu", 
        favorite_cities=favorite_cities
    )

@app.route('/weather', methods=['GET'])
def weather_api():
    """API endpoint to get current weather AND forecast data."""
    city = request.args.get('city')
    if not city:
        return jsonify({"error": "Please provide a city name."}), 400
    
    current_weather_info = get_weather_data(city)
    
    # Check for errors in the current weather data (primary check)
    if "error" in current_weather_info:
        return jsonify(current_weather_info), 404
    
    forecast_info = get_forecast_data(city)
    
    # Combine the data
    response_data = {
        'current': current_weather_info,
        'forecast': forecast_info
    }
    
    return jsonify(response_data)

@app.route('/favorites/add', methods=['POST'])
def add_favorite():
    """Handles adding a new city to the database."""
    city_name = request.form.get('city_name')
    
    if city_name:
        city_name_title = city_name.title().strip()
        if FavoriteCity.query.filter_by(city_name=city_name_title).first():
            return "City already saved!", 409
        
        new_favorite = FavoriteCity(city_name=city_name_title)
        db.session.add(new_favorite)
        db.session.commit()
        return jsonify({"message": f"{city_name_title} added to favorites!"}), 201
    
    return "City name is required.", 400

@app.route('/favorites/remove/<int:city_id>', methods=['POST'])
def remove_favorite(city_id):
    """Handles removing a city from the database by ID."""
    try:
        city_to_delete = FavoriteCity.query.get_or_404(city_id)
        db.session.delete(city_to_delete)
        db.session.commit()
        return jsonify({"message": f"{city_to_delete.city_name} removed."}), 200
    except Exception:
        return "Error removing favorite.", 500


if __name__ == '__main__':
    # --- Database Initialization ---
    with app.app_context():
        db.create_all()
        print("Database initialized and tables created.")
    
    app.run(debug=True)