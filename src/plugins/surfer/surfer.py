from datetime import datetime, timezone, timedelta
import json
import logging
import pandas as pd
from plugins.base_plugin.base_plugin import BasePlugin
import pytz
import requests

logger = logging.getLogger(__name__)

SIM_API = True
SURF_DATA_URL = "https://api.stormglass.io/v2/weather/point"
# TODO: Eventually these should be settings passed in from the UI
HARDCODED_SURF_PARAMS = ['swellDirection', 'swellHeight', 'swellPeriod', 'waterTemperature', 'waveDirection', 'waveHeight', 'wavePeriod']

# Where I left off: Data is available, currently simmed (not tested on pi), should try throwing it into some graphs to display :) Have a good day

class Surfer(BasePlugin):
    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        template_params['storm_glass_api_key'] = {
            "required": True,
            "service": "StormGlass",
            "expected_key": "STORM_GLASS_SECRET"
        }
        template_params['style_settings'] = True
        return template_params

    def generate_image(self, settings, device_config):
        # TODO: to limit API usage, look into caching data so calls are only made once per day
        lat = settings.get('latitude')
        long = settings.get('longitude')
        if not lat or not long:
            raise RuntimeError("Latitude and Longitude are required.")

        weather_provider = settings.get('weatherProvider', 'OpenWeatherMap')
        title = settings.get('customTitle', '')

        timezone = device_config.get_config("timezone", default="America/New_York")
        time_format = device_config.get_config("time_format", default="12h")
        tz = pytz.timezone(timezone)

        start_time = datetime.now()
        end_time = start_time + timedelta(days=1)
        formatted_start_time = start_time.strftime("%Y-%m-%dT00:00:00")
        formatted_end_time = end_time.strftime("%Y-%m-%dT00:00:00")

        # Gather and parse surf data
        try:
            storm_glass_api_key = device_config.load_env_key("STORM_GLASS_SECRET")
            if not storm_glass_api_key:
                raise RuntimeError('Storm Glass API Key not configured')
            surf_data = self.get_surf_data(lat, long, formatted_start_time, formatted_end_time, storm_glass_api_key)
            parsed_surf_data = self.parse_surf_data(surf_data)

            # TODO need to take the surf data and add it to a template params dict, each measurement can be its own entry
            template_params = {
                'title': 'The Big MB',
                'current_date': start_time.strftime("%A, %B %d"),
                'ai_summary': self.get_ai_surf_summary(parsed_surf_data, True),
                'times': [t.strftime("%H:00") for t in parsed_surf_data['time'].tolist()],
                'water_temperatures': parsed_surf_data['waterTemperature'].tolist()
            }
        except Exception as e:
            logger.error(f'Storm Glass request failed: {str(e)}')
            raise RuntimeError('Storm Glass request failure, please check logs.')

        # Have language model summarize

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
    def get_surf_data(self, lat, long, start_time, end_time, api_key):
        response = None
        if SIM_API:
            logging.info('Simming Storm Glass API response')
            test_json_file_path = self.get_plugin_dir('WeatherRequestResponseRaw.json')
            with open(test_json_file_path, "r") as f:
                response = json.load(f)
            return response
        else:
            response = requests.get(
                SURF_DATA_URL,
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
                logging.error(f"Failed to retrieve surf data: {response.content}")
                raise RuntimeError("Failed to retrieve surf data.")
            else:
                return response.json()

    # Returns a dataframe of the hourly data sorted by time in the form:
    #   YYYY-MM-DD HH:MM:SS+00:00   - swellHeight - waterTemperature - ... - < Measurement X >
    #   ...
    #   YYYY-MM-DD+1 HH:MM:SS+00:00 - swellHeight - waterTemperature - ... - < Measurement X >
    # Note the order of the measurements after the time column is not guaranteed, but it shouldn't be an issue
    def parse_surf_data(self, surf_data):
        # JSON is returned with 'hours' object containing the data and 'meta' object we do not need
        hours = surf_data["hours"]

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

    def get_ai_surf_summary(self, surf_data, do_surfer_bro):
        # TODO make API call to AI service with the prompt below and appended surf data
        surfer_bro_prompt = 'Your response should be made as a stereotypical California surfer dude and should use American surfer slang.'
        prompt = 'Given the following surf and weather data, generate a one sentence summary of the conditions for the day.{bro_prompt} The second sentence should concisely give the best time(s) to go surfing for the day, if any, if there are no good times, the second sentence should be omitted. Sentences should be short and not contain any new lines or breaks between them. {data}'
        prompt = prompt.format(bro_prompt = surfer_bro_prompt if do_surfer_bro else '', data=surf_data)

        # TODO AI call here, returning placeholder until then

        return f'Morning’s blown out mush, dude, not worth the paddle. Best window’s 7–9pm when it cleans up. ({datetime.now()})'