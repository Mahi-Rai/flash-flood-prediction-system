import logging
from typing import Optional, Dict, Any, List

import requests

logger = logging.getLogger("pahad_rakshak_weather_service")

OPEN_METEO_BASE_URL = "https://api.open-meteo.com/v1/forecast"
REQUEST_TIMEOUT_SECONDS = 8


class WeatherService:
    """
    Thin wrapper around the Open-Meteo free forecast API (no API key required).
    Used to pull real current/1h and trailing-24h rainfall totals for a given
    lat/lng, so ward telemetry can be grounded in real weather instead of
    pure simulation.
    """

    @staticmethod
    def fetch_rainfall_data(lat: float, lng: float) -> Optional[Dict[str, Any]]:
        """
        Returns a dict:
            {
                "rainfall_1h_mm": float,
                "rainfall_24h_mm": float,
                "temperature_c": float,
                "source": "open-meteo"
            }
        or None if the request failed / data was unavailable, so callers can
        fall back to simulated values gracefully.
        """
        params = {
            "latitude": lat,
            "longitude": lng,
            "current": "precipitation,rain,temperature_2m",
            "hourly": "precipitation",
            "past_days": 1,
            "forecast_days": 1,
            "timezone": "UTC",
        }

        try:
            resp = requests.get(OPEN_METEO_BASE_URL, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            logger.warning(f"Open-Meteo request failed for ({lat}, {lng}): {e}")
            return None
        except ValueError as e:
            logger.warning(f"Open-Meteo returned invalid JSON for ({lat}, {lng}): {e}")
            return None

        try:
            current = data.get("current", {})
            rainfall_1h_mm = float(current.get("precipitation", 0.0) or 0.0)
            temperature_c = float(current.get("temperature_2m", 0.0) or 0.0)

            rainfall_24h_mm = WeatherService._sum_trailing_24h_precipitation(data)

            return {
                "rainfall_1h_mm": round(rainfall_1h_mm, 2),
                "rainfall_24h_mm": round(rainfall_24h_mm, 2),
                "temperature_c": round(temperature_c, 1),
                "source": "open-meteo",
            }
        except (KeyError, TypeError, ValueError) as e:
            logger.warning(f"Failed to parse Open-Meteo response for ({lat}, {lng}): {e}")
            return None

    @staticmethod
    def _sum_trailing_24h_precipitation(data: Dict[str, Any]) -> float:
        """
        Sums the 24 hourly precipitation values ending at (or nearest to) the
        current reported time, using the hourly series returned alongside
        `past_days=1`.
        """
        hourly = data.get("hourly", {})
        times: List[str] = hourly.get("time", [])
        precip: List[Optional[float]] = hourly.get("precipitation", [])
        current_time = data.get("current", {}).get("time")

        if not times or not precip:
            return 0.0

        if current_time and current_time in times:
            end_idx = times.index(current_time)
        else:
            # Fall back to the last available index if exact match isn't found
            end_idx = len(times) - 1

        start_idx = max(0, end_idx - 23)
        window = precip[start_idx:end_idx + 1]
        return sum(v for v in window if isinstance(v, (int, float)))

    @staticmethod
    def compute_ward_centroid(ward: Dict[str, Any]) -> Optional[tuple]:
        """
        Best-effort extraction of a (lat, lng) centroid for a ward record.
        Tries direct lat/lng fields first, then falls back to averaging the
        ward's polygon points. Returns None if no usable coordinates exist.
        """
        for lat_key, lng_key in (("lat", "lng"), ("latitude", "longitude"), ("centroid_lat", "centroid_lng")):
            if lat_key in ward and lng_key in ward:
                try:
                    return float(ward[lat_key]), float(ward[lng_key])
                except (TypeError, ValueError):
                    pass

        polygon = ward.get("polygon")
        if polygon and isinstance(polygon, list) and len(polygon) > 0:
            try:
                lats = []
                lngs = []
                for point in polygon:
                    if isinstance(point, dict):
                        lats.append(float(point.get("lat")))
                        lngs.append(float(point.get("lng")))
                    elif isinstance(point, (list, tuple)) and len(point) == 2:
                        lats.append(float(point[0]))
                        lngs.append(float(point[1]))
                if lats and lngs:
                    return sum(lats) / len(lats), sum(lngs) / len(lngs)
            except (TypeError, ValueError):
                return None

        return None
