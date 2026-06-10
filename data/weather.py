"""
data/weather.py

Fetches weather forecast for WC2026 match venues.
Uses Open-Meteo API -- completely free, no API key needed.
Venue coordinates resolved from Sportmonks venue_id.
"""

from __future__ import annotations
import requests
from datetime import datetime
from config import settings


# --- WC2026 venue coordinates ------------------------------------------------
# Hardcoded by venue_id from Sportmonks -- these are fixed for the tournament.
# lat, lon, city, stadium_name

VENUE_COORDS: dict[int, tuple[float, float, str, str]] = {
    1599:  (19.3029,  -99.1506,  "Mexico City",    "Estadio Azteca"),
    1519:  (26.8354,  -80.0706,  "Miami",          "Hard Rock Stadium"),
    8787:  (40.8135,  -74.0745,  "New York/NJ",    "MetLife Stadium"),
    8879:  (32.7480,  -97.0930,  "Dallas",         "AT&T Stadium"),
    8878:  (33.9535, -118.3392,  "Los Angeles",    "SoFi Stadium"),
    8880:  (37.4033, -121.9694,  "San Francisco",  "Levi's Stadium"),
    8881:  (39.0489,  -94.4839,  "Kansas City",    "Arrowhead Stadium"),
    8882:  (42.0909,  -71.2643,  "Boston",         "Gillette Stadium"),
    8883:  (39.9008,  -75.1675,  "Philadelphia",   "Lincoln Financial Field"),
    8884:  (35.2258,  -80.8528,  "Charlotte",      "Bank of America Stadium"),
    8885:  (33.7554,  -84.4008,  "Atlanta",        "Mercedes-Benz Stadium"),
    8886:  (29.6847,  -95.4107,  "Houston",        "NRG Stadium"),
    8887:  (20.6867, -103.4667,  "Guadalajara",    "Estadio Akron"),
    8888:  (25.6694, -100.4678,  "Monterrey",      "Estadio BBVA"),
    8889:  (49.2768, -123.1118,  "Vancouver",      "BC Place"),
    8890:  (43.6333,  -79.4183,  "Toronto",        "BMO Field"),
}


# --- Weather fetch -----------------------------------------------------------

def get_match_weather(
    venue_id:     int | None = None,
    kickoff_date: str | None = None,
) -> dict:
    """
    Fetch weather forecast for a match venue.

    Args:
        venue_id:     Sportmonks venue_id from fixture metadata
        kickoff_date: "YYYY-MM-DD" string (uses today if None)

    Returns:
        {
            "venue":        str | None,
            "city":         str | None,
            "date":         str,
            "temp_c":       float | None,
            "temp_f":       float | None,
            "condition":    str | None,
            "wind_kph":     float | None,
            "precip_mm":    float | None,
            "summary":      str,
            "available":    bool,
        }
    """
    # resolve venue coordinates
    if venue_id is None or venue_id not in VENUE_COORDS:
        return _unavailable(
            reason=f"venue_id {venue_id} not in WC2026 venue list"
        )

    lat, lon, city, stadium = VENUE_COORDS[venue_id]

    # resolve date
    if kickoff_date is None:
        kickoff_date = datetime.utcnow().strftime("%Y-%m-%d")

    try:
        r = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude":   lat,
                "longitude":  lon,
                "daily":      ",".join([
                    "temperature_2m_max",
                    "temperature_2m_min",
                    "precipitation_sum",
                    "windspeed_10m_max",
                ]),
                "timezone":   "UTC",
                "start_date": kickoff_date,
                "end_date":   kickoff_date,
            },
            timeout=10,
        )
        r.raise_for_status()
        data  = r.json()
        daily = data.get("daily", {})

        temp_max = (daily.get("temperature_2m_max") or [None])[0]
        temp_min = (daily.get("temperature_2m_min") or [None])[0]
        precip   = (daily.get("precipitation_sum")  or [None])[0]
        wind     = (daily.get("windspeed_10m_max")  or [None])[0]

        if temp_max is None:
            return _unavailable(reason="Open-Meteo returned no data")

        temp_c    = round((temp_max + temp_min) / 2, 1)
        temp_f    = round(temp_c * 9 / 5 + 32, 1)
        condition = _condition(temp_c, precip, wind)

        return {
            "venue":     stadium,
            "city":      city,
            "date":      kickoff_date,
            "temp_c":    temp_c,
            "temp_f":    temp_f,
            "condition": condition,
            "wind_kph":  wind,
            "precip_mm": precip,
            "summary": (
                f"{stadium} ({city}): {temp_c}°C / {temp_f}°F, "
                f"{condition}, wind {wind} km/h, precip {precip} mm"
            ),
            "available": True,
        }

    except Exception as e:
        return _unavailable(reason=str(e))


# --- Helpers -----------------------------------------------------------------

def _unavailable(reason: str = "") -> dict:
    return {
        "venue":     None,
        "city":      None,
        "date":      None,
        "temp_c":    None,
        "temp_f":    None,
        "condition": None,
        "wind_kph":  None,
        "precip_mm": None,
        "summary":   f"Weather data not available. {reason}".strip(),
        "available": False,
    }


def _condition(temp_c: float, precip: float | None, wind: float | None) -> str:
    """Derive a plain English condition string."""
    parts = []

    if precip is not None and precip > 5:
        parts.append("rainy")
    elif precip is not None and precip > 1:
        parts.append("light rain")
    else:
        parts.append("dry")

    if wind is not None and wind > 40:
        parts.append("very windy")
    elif wind is not None and wind > 20:
        parts.append("windy")

    if temp_c > 35:
        parts.append("very hot")
    elif temp_c > 28:
        parts.append("hot")
    elif temp_c < 10:
        parts.append("cold")

    return ", ".join(parts)