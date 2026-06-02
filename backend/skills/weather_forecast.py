"""PA-63 — 5-day weather forecast: "weather forecast" / "weather this week"."""
from __future__ import annotations
import re
from datetime import date

from backend.core.http_client import get as http_get
from backend.skills.weather import _geocode, _WMO

META = {
    "name": "weather_forecast",
    "description": "Returns a 5-day weather forecast for a city.",
    "triggers": [
        "weather forecast",
        "5 day forecast",
        "five day forecast",
        "weather this week",
        "weather tomorrow",
        "forecast for",
        "weekly forecast",
        "what will the weather be",
        "forecast today",
    ],
}

_CITY_RE = re.compile(
    r"(?:forecast\s+(?:for|in)|weather\s+(?:forecast\s+)?(?:for|in|tomorrow\s+in))\s+"
    r"([a-zA-Z][a-zA-Z\s\-]+?)(?:\s*[?.!])?$",
    re.I,
)
_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def run(args: dict | None = None) -> str:
    utterance = ((args or {}).get("utterance") or "").strip()

    m = _CITY_RE.search(utterance)
    city = m.group(1).strip() if m else "Moers"

    try:
        loc = _geocode(city)
        if not loc:
            return f"I couldn't find {city}."
        lat, lon, name = loc

        resp = http_get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "daily": "temperature_2m_max,temperature_2m_min,weather_code",
                "timezone": "auto",
                "forecast_days": "5",
            },
        )
        resp.raise_for_status()
        daily = resp.json().get("daily", {})
        dates = daily.get("time", [])
        maxtemps = daily.get("temperature_2m_max", [])
        mintemps = daily.get("temperature_2m_min", [])
        codes = daily.get("weather_code", [])

        today = date.today()
        parts = []
        for i, d in enumerate(dates[:5]):
            dt = date.fromisoformat(d)
            if i == 0:
                day_label = "Today"
            elif i == 1:
                day_label = "Tomorrow"
            else:
                day_label = _DAYS[dt.weekday()]
            desc = _WMO.get(codes[i], "mixed conditions")
            parts.append(
                f"{day_label}: {desc}, {mintemps[i]:.0f} to {maxtemps[i]:.0f} degrees"
            )

        return f"5-day forecast for {name}. " + "; ".join(parts) + "."

    except Exception as e:
        return f"I couldn't get the forecast: {e}"


def self_test() -> bool:
    return True
