"""PA-56 — Unit converter: "convert 5 miles to km" / "how many kg is 10 pounds"."""
from __future__ import annotations
import re

META = {
    "name": "unit_converter",
    "description": "Converts between common units of length, weight, temperature, and volume.",
    "triggers": [
        "convert ",
        "how many ",
        "how much is ",
        "in kilometers",
        "in miles",
        "in celsius",
        "in fahrenheit",
        "in kilograms",
        "in pounds",
        "in liters",
        "in gallons",
        "to km",
        "to miles",
        "to kg",
        "to pounds",
        "to celsius",
        "to fahrenheit",
    ],
}

# (factor to base unit, base unit name)
_UNITS: dict[str, tuple[float, str]] = {
    # length — base: meter
    "meter": (1.0, "meter"), "meters": (1.0, "meter"), "m": (1.0, "meter"),
    "kilometer": (1000.0, "meter"), "kilometers": (1000.0, "meter"), "km": (1000.0, "meter"),
    "mile": (1609.344, "meter"), "miles": (1609.344, "meter"),
    "foot": (0.3048, "meter"), "feet": (0.3048, "meter"), "ft": (0.3048, "meter"),
    "inch": (0.0254, "meter"), "inches": (0.0254, "meter"), "in": (0.0254, "meter"),
    "yard": (0.9144, "meter"), "yards": (0.9144, "meter"), "yd": (0.9144, "meter"),
    "centimeter": (0.01, "meter"), "centimeters": (0.01, "meter"), "cm": (0.01, "meter"),
    # weight — base: kilogram
    "kilogram": (1.0, "kilogram"), "kilograms": (1.0, "kilogram"), "kg": (1.0, "kilogram"),
    "gram": (0.001, "kilogram"), "grams": (0.001, "kilogram"), "g": (0.001, "kilogram"),
    "pound": (0.453592, "kilogram"), "pounds": (0.453592, "kilogram"), "lb": (0.453592, "kilogram"), "lbs": (0.453592, "kilogram"),
    "ounce": (0.0283495, "kilogram"), "ounces": (0.0283495, "kilogram"), "oz": (0.0283495, "kilogram"),
    "ton": (1000.0, "kilogram"), "tons": (1000.0, "kilogram"),
    # volume — base: liter
    "liter": (1.0, "liter"), "liters": (1.0, "liter"), "l": (1.0, "liter"),
    "milliliter": (0.001, "liter"), "milliliters": (0.001, "liter"), "ml": (0.001, "liter"),
    "gallon": (3.78541, "liter"), "gallons": (3.78541, "liter"),
    "cup": (0.236588, "liter"), "cups": (0.236588, "liter"),
    "pint": (0.473176, "liter"), "pints": (0.473176, "liter"),
}

_TEMP_FROM = {"celsius", "c", "centigrade", "fahrenheit", "f", "kelvin", "k"}
_TEMP_PATTERN = re.compile(
    r"(-?\d+(?:\.\d+)?)\s*(celsius|fahrenheit|kelvin|[cfk])\b.*\bto\s+(celsius|fahrenheit|kelvin|[cfk])\b",
    re.I,
)
_CONVERT_PATTERN = re.compile(
    r"(-?\d+(?:\.\d+)?)\s*([a-z]+)\b.*\bto\s+([a-z]+)\b",
    re.I,
)


def _temp(value: float, src: str, dst: str) -> float:
    s, d = src.lower()[0], dst.lower()[0]
    if s == "c":
        kelvin = value + 273.15
    elif s == "f":
        kelvin = (value + 459.67) * 5 / 9
    else:
        kelvin = value
    if d == "c":
        return kelvin - 273.15
    elif d == "f":
        return kelvin * 9 / 5 - 459.67
    return kelvin


def _fmt(value: float) -> str:
    if abs(value) >= 1000:
        return f"{value:,.2f}".rstrip("0").rstrip(".")
    if abs(value) < 0.01:
        return f"{value:.6f}".rstrip("0").rstrip(".")
    return f"{value:.4f}".rstrip("0").rstrip(".")


def run(args: dict | None = None) -> str:
    utterance = (args or {}).get("utterance", "")

    # Temperature
    m = _TEMP_PATTERN.search(utterance)
    if m:
        value, src, dst = float(m.group(1)), m.group(2), m.group(3)
        result = _temp(value, src, dst)
        return f"{_fmt(value)} {src} is {_fmt(result)} {dst}."

    # General unit conversion
    m = _CONVERT_PATTERN.search(utterance)
    if not m:
        # No number-and-unit pair, so this is not a conversion. "how many "
        # has to be a trigger to catch "how many km in 5 miles", and it also
        # begins "how many hours should I sleep" — a question for the LLM.
        return None

    value, src_str, dst_str = float(m.group(1)), m.group(2).lower(), m.group(3).lower()

    src = _UNITS.get(src_str)
    dst = _UNITS.get(dst_str)

    if not src:
        return f"I don't know the unit '{src_str}'."
    if not dst:
        return f"I don't know the unit '{dst_str}'."
    if src[1] != dst[1]:
        return f"Can't convert {src_str} to {dst_str} — they measure different things."

    result = value * src[0] / dst[0]
    return f"{_fmt(value)} {src_str} is {_fmt(result)} {dst_str}."


def self_test() -> bool:
    r = run({"utterance": "convert 1 kilometer to meters"})
    return "1,000" in r or "1000" in r
