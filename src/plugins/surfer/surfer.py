from datetime import datetime, timezone, timedelta
import json
import logging
from openai import OpenAI
import pandas as pd
from plugins.base_plugin.base_plugin import BasePlugin
import pytz
import requests

logger = logging.getLogger(__name__)

WEATHER_DATA_URL = "https://api.stormglass.io/v2/weather/point"
TIDE_DATA_URL = "https://api.stormglass.io/v2/tide/extremes/point"
GEOCODING_URL = "http://api.openweathermap.org/geo/1.0/reverse?lat={lat}&lon={long}&limit=1&appid={api_key}"

# TODO: Eventually these should be settings passed in from the UI
HARDCODED_SURF_PARAMS = ['swellDirection', 'swellHeight', 'swellPeriod', 'waterTemperature', 'waveDirection', 'waveHeight', 'wavePeriod', 'windSpeed', 'windDirection']

class Surfer(BasePlugin):
    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        # Template just looks for the param 'api_key' to see if it needs the banner on the settings page
        template_params['api_key'] = {
            "required": True,
            "service": "OpenWeatherMap, StormGlass, OpenAI (optional)",
            "expected_key": "OPEN_WEATHER_MAP_SECRET, STORM_GLASS_SECRET, OPEN_AI_SECRET (optional)"
        }
        template_params['style_settings'] = True
        return template_params

    def generate_image(self, settings, device_config):
        # TODO: to limit API usage, look into caching data so calls are only made once per day
        lat = settings.get('latitude')
        long = settings.get('longitude')
        if not lat or not long:
            raise RuntimeError("Latitude and Longitude are required.")

        units = settings.get('units')
        if not units or units not in ['metric', 'imperial', 'standard']:
            raise RuntimeError("Units are required.")

        timezone = device_config.get_config("timezone", default="America/New_York")
        time_format = device_config.get_config("time_format", default="12h")
        tz = pytz.timezone(timezone)

        start_time = datetime.now()
        end_time = start_time + timedelta(days=1)
        formatted_start_time = start_time.strftime("%Y-%m-%dT00:00:00")
        formatted_end_time = end_time.strftime("%Y-%m-%dT00:00:00")

        do_surfer_bro = settings.get('summaryStyle', '') == 'surfer'

        # Gather and parse surf data
        try:
            sim_api_responses = device_config.load_env_key("SIM_SURF_API") or False

            # Get API Keys
            open_weather_map_api_key = device_config.load_env_key("OPEN_WEATHER_MAP_SECRET")
            if not open_weather_map_api_key:
                raise RuntimeError('Open Weather Map API Key not configured')
            storm_glass_api_key = device_config.load_env_key("STORM_GLASS_SECRET")
            if not storm_glass_api_key:
                raise RuntimeError('Storm Glass API Key not configured')
            openai_api_key = device_config.load_env_key("OPEN_AI_SECRET")

            title = settings.get('customTitle', '')
            if settings.get('titleSelection', 'location') == 'location':
                title = self.get_location(open_weather_map_api_key, lat, long)

            raw_weather_data = self.get_surf_weather_data(lat, long, formatted_start_time, formatted_end_time, storm_glass_api_key, sim_api_responses)
            raw_tide_data = self.get_surf_tide_data(lat, long, formatted_start_time, formatted_end_time, storm_glass_api_key, sim_api_responses)
            parsed_weather_data = self.parse_surf_data(raw_weather_data)
            parsed_tide_data = self.parse_surf_data(raw_tide_data)

            # Format times once since they are used in multiple places
            if time_format == "24h":
                formatted_times = [t.strftime("%H:00") for t in parsed_weather_data['time'].tolist()]
                tide_times = [t.strftime("%H:%M") for t in parsed_tide_data['time'].tolist()]
            else:
                formatted_times = [t.strftime("%-I %p") for t in parsed_weather_data['time'].tolist()]
                tide_times = [t.strftime("%-I:%M %p") for t in parsed_tide_data['time'].tolist()]

            # Convert wind direction (0-360 deg) to compass directions
            parsed_weather_data['windDirectionCompass'] = parsed_weather_data['windDirection'].apply(self.degrees_to_compass)

            # Apply unit selection
            parsed_weather_data = self.apply_units(parsed_weather_data, units)

            # TODO need to take the surf data and add it to a template params dict, each measurement can be its own entry
            template_params = {
                'title': title,
                'current_date': start_time.strftime("%A, %B %d"),
                'times': formatted_times,
                'tide_times': tide_times,
                'tide_heights': parsed_tide_data['height'].tolist(),
                'water_temperatures': parsed_weather_data['waterTemperature'].tolist(),
                'wave_heights': parsed_weather_data['waveHeight'].tolist(),
                'swell_heights': parsed_weather_data['swellHeight'].tolist(),
                'wave_periods': parsed_weather_data['wavePeriod'].tolist(),
                'wind_conditions': self.build_wind_conditions(formatted_times, parsed_weather_data['windSpeed'].tolist(), parsed_weather_data['windDirectionCompass'].tolist()),
                'avg_water_temp': f"{parsed_weather_data['waterTemperature'].mean():.1f}",
                'swell_height_highlow_str': f"{parsed_weather_data['swellHeight'].max():0.1f} / {parsed_weather_data['swellHeight'].min():0.1f}",
                'wave_height_highlow_str': f"{parsed_weather_data['waveHeight'].max():0.1f} / {parsed_weather_data['waveHeight'].min():0.1f}",
                'wave_period_highlow_str': f"{parsed_weather_data['wavePeriod'].max():0.1f} / {parsed_weather_data['wavePeriod'].min():0.1f}",
                'units': units,
            }
        except Exception as e:
            logger.error(f'Storm Glass request failed: {str(e)}')
            raise RuntimeError('Storm Glass request failure, please check logs.')

        if settings.get('displaySummary', "false") == "true":
            template_params['ai_summary'] = self.get_ai_surf_summary(parsed_weather_data, parsed_tide_data, do_surfer_bro, openai_api_key)

        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]

        template_params["plugin_settings"] = settings

        # Add last refresh time
        now = datetime.now(tz)
        if time_format == "24h":
            last_refresh_time = now.strftime("%Y-%m-%d %H:%M")
        else:
            last_refresh_time = now.strftime("%Y-%m-%d %I:%M %p")
        template_params["last_refresh_time"] = last_refresh_time

        image = self.render_image(dimensions, "surfer.html", "surfer.css", template_params)

        if not image:
            raise RuntimeError("Failed to take screenshot, please check logs.")
        return image

    # Returns the raw json response of {hours: { <array of 25 data points for each hour (00 - 23 and 00 for next day) }, meta: { misc API info }}
    def get_surf_weather_data(self, lat, long, start_time, end_time, api_key, sim_response=False):
        response = None
        if sim_response:
            logging.info('Simming Storm Glass Weather API response')
            test_json_file_path = self.get_plugin_dir('WeatherRequestResponseRaw.json')
            with open(test_json_file_path, "r") as f:
                response = json.load(f)
            return response
        else:
            response = requests.get(
                WEATHER_DATA_URL,
                params={
                    'start': start_time,
                    'end': end_time,
                    'lat':lat,
                    'lng':long,
                    'params': ','.join(HARDCODED_SURF_PARAMS),
                },
                headers={
                    'Authorization': api_key
                }
            )

            if not 200 <= response.status_code < 300:
                logging.error(f"Failed to retrieve weather data: {response.content}")
                raise RuntimeError("Failed to retrieve weather data.")
            else:
                return response.json()

    def get_surf_tide_data(self, lat, long, start_time, end_time, api_key, sim_response=False):
        response = None
        if sim_response:
            logging.info('Simming Storm Glass Tide API response')
            test_json_file_path = self.get_plugin_dir('TideRequestResponseRaw.json')
            with open(test_json_file_path, "r") as f:
                response = json.load(f)
            return response
        else:
            response = requests.get(
                TIDE_DATA_URL,
                params={
                    'lat': lat,
                    'lng': long,
                    'start': start_time,
                    'end': end_time,
                },
                headers={
                    'Authorization': api_key
                }
            )

            if not 200 <= response.status_code < 300:
                logging.error(f"Failed to retrieve tide data: {response.content}")
                raise RuntimeError("Failed to retrieve tide data.")
            else:
                return response.json()

    # Returns a dataframe of the hourly data sorted by time in the form:
    #   YYYY-MM-DD HH:MM:SS+00:00   - swellHeight - waterTemperature - ... - < Measurement X >
    #   ...
    #   YYYY-MM-DD+1 HH:MM:SS+00:00 - swellHeight - waterTemperature - ... - < Measurement X >
    # Note the order of the measurements after the time column is not guaranteed, but it shouldn't be an issue
    def parse_surf_data(self, surf_data):
        # JSON is returned with 'hours' object containing the data and 'meta' object we do not need
        try:
            hours = surf_data["hours"]
        except KeyError:
            # Tide data is under a data object instead of an hours object like the weather data
            hours = surf_data["data"]

        # Need to determine which measurements were provided in order to average the same ones from different sources
        # Excludes the "time" value for each object
        # TODO: Could probably make the measurements a setting and then the list can just be passed along
        all_fields = set()
        for entry in hours:
            all_fields.update(k for k in entry.keys() if k != "time")

        # Average measurements from different sources, ex. waterTemperature.noaa and waterTemperature.eg into waterTemperature
        rows = []
        for entry in hours:
            row = {}
            row["time"] = pd.to_datetime(entry["time"])
            for field in all_fields:
                if field in entry and isinstance(entry[field], dict):
                    values = [v for v in entry[field].values() if isinstance(v, (int, float))]
                    if values:  # avoid empty dicts or non-numeric
                        row[field] = sum(values) / len(values)
                elif field in entry and isinstance(entry[field], (int, float)):
                    # if a field is directly numeric
                    row[field] = entry[field]
            rows.append(row)

        df = pd.DataFrame(rows)

        # Sort by time
        df = df.sort_values("time").reset_index(drop=True)

        # TODO: Handle converting the time to 12H or 24H
        # TODO: Handle converting units such as temp from C to F (API sends C)

        return df

    def get_ai_surf_summary(self, weather_data, tide_data, do_surfer_bro, api_key):
        logger.info("get_ai_surf_summary called")
        if not api_key:
            raise RuntimeError('Show Summary selected, but no OpenAI API key was found')

        surfer_bro_prompt = 'Your response should be made as a stereotypical California surfer dude and should use American surfer slang.'
        system_prompt = 'You are an expert surf weather analyst. The user will provide you JSON weather data and JSON tide data. Given the following surf and weather data, generate a one sentence summary of the conditions for the day.{bro_prompt} The second sentence should concisely give the best time(s) to go surfing for the day, if any, if there are no good times, the second sentence should be omitted. Sentences should be short and not contain any new lines or breaks between them. Do not directly mention any measurements or the date, only summarize. Your entire response should be brief.'
        system_prompt = system_prompt.format(bro_prompt = surfer_bro_prompt if do_surfer_bro else '')
        model = 'gpt-4o'
        try:
            ai_client = OpenAI(api_key=api_key)

            response = ai_client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": system_prompt
                    },
                    {
                        "role": "user",
                        "content": f"weather_data={weather_data} tide_data={tide_data}"
                    }
                ],
                temperature=1
            )

            summary = response.choices[0].message.content.strip()
            logger.info(f"Generated the following summary: {summary}")

        except Exception as e:
            logger.error(f"Failed to make Open AI request: {str(e)}")
            raise RuntimeError("Open AI request failure, please check logs.")

        return summary

    def degrees_to_compass(self, degrees):
        directions = [
            "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"
        ]

        index = round((degrees % 360) / 22.5)

        return directions[index % 16]

    def build_wind_conditions(self, times, wind_speeds, wind_direction_compass):
        conditions = []

        for index in range(7):
            # We need to grab indices 0, 4, 8, 12, 16, 20, 24
            actual_index = index * 4

            conditions.append(
                {
                    'time': times[actual_index],
                    'speed': f"{wind_speeds[actual_index]:.1f}",
                    'direction': wind_direction_compass[actual_index]
                }
            )

        return conditions

    def get_location(self, api_key, lat, long):
        url = GEOCODING_URL.format(lat=lat, long=long, api_key=api_key)
        response = requests.get(url)

        if not 200 <= response.status_code < 300:
            logging.error(f"Failed to get location: {response.content}")
            raise RuntimeError("Failed to retrieve location.")

        location_data = response.json()[0]
        location_str = f"{location_data.get('name')}, {location_data.get('state', location_data.get('country'))}"

        return location_str

    def apply_units(self, weather_data, units):
        # Water Temp Data comes in as C
        weather_data['waterTemperature'] = weather_data['waterTemperature'].apply(
            lambda temp_c: temp_c if units == 'metric' else
            ((temp_c * 9 / 5) + 32) if units == 'imperial' else
            (temp_c + 273.15))

        # Swell Height Data comes in as meters
        weather_data['swellHeight'] = weather_data['swellHeight'].apply(
            lambda swell_m: swell_m if units == 'metric' else
            (swell_m * 3.28084) if units == 'imperial' else
            swell_m)

        # Wave Height Data comes in as meters
        weather_data['waveHeight'] = weather_data['waveHeight'].apply(
            lambda wave_height_m: wave_height_m if units == 'metric' else
            (wave_height_m * 3.28084) if units == 'imperial' else
            wave_height_m)

        # Wind Speed Data comes in as km/h
        weather_data['windSpeed'] = weather_data['windSpeed'].apply(
            lambda wind_speed_kmh: wind_speed_kmh if units == 'metric' else
            (wind_speed_kmh * 0.621371) if units == 'imperial' else
            wind_speed_kmh)

        return weather_data
