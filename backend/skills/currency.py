"""Currency converter skill — Frankfurter API (free, no key needed).

Examples:
  "convert 100 USD to EUR"
  "how much is 50 euros in dollars"
  "100 Dollar in Euro"
"""
from __future__ import annotations
import re

from backend.core.http_client import get as http_get

META = {
    "name": "currency",
    "description": "Convert between currencies using live exchange rates.",
    "triggers": [
        # English
        "convert currency",
        "convert to",
        "convert from",
        "how much is",
        "exchange rate",
        "currency conversion",
        "in dollars",
        "in euros",
        "in pounds",
        "usd to",
        "eur to",
        "gbp to",
        "chf to",
        "jpy to",
        "to usd",
        "to eur",
        "to gbp",
        # German
        "in euro umrechnen",
        "in dollar umrechnen",
        "umrechnen",
        "wechselkurs",
        "dollar in euro",
        "euro in dollar",
        "in euro",
        "in dollar",
    ],
    "example_utterances": [
        "Convert 100 USD to EUR",
        "How much is 50 euros in dollars?",
        "Exchange rate USD to GBP",
        "100 Dollar in Euro",
    ],
}

# Currency code normalization
_ALIASES: dict[str, str] = {
    "dollar": "USD", "dollars": "USD", "us dollar": "USD", "usd": "USD",
    "euro": "EUR", "euros": "EUR", "eur": "EUR",
    "pound": "GBP", "pounds": "GBP", "british pound": "GBP", "gbp": "GBP",
    "franc": "CHF", "francs": "CHF", "swiss franc": "CHF", "chf": "CHF",
    "yen": "JPY", "jpy": "JPY", "japanese yen": "JPY",
    "yuan": "CNY", "cny": "CNY", "renminbi": "CNY",
    "ruble": "RUB", "rubles": "RUB", "rub": "RUB",
    "won": "KRW", "krw": "KRW",
    "rupee": "INR", "rupees": "INR", "inr": "INR",
    "real": "BRL", "reais": "BRL", "brl": "BRL",
    "krona": "SEK", "sek": "SEK", "kronor": "SEK",
    "krone": "DKK", "dkk": "DKK",
    "norwegian krone": "NOK", "nok": "NOK",
    "canadian dollar": "CAD", "cad": "CAD",
    "australian dollar": "AUD", "aud": "AUD",
    "swiss": "CHF",
}

# "100 USD to EUR" / "convert 50 euros to dollars"
_PATTERN = re.compile(
    r"(?:convert\s+)?(\d+(?:[.,]\d+)?)\s*"
    r"(dollars?|euros?|pounds?|francs?|yen|yuan|rubles?|won|rupees?|reais?|real|"
    r"krona|kronor|krone|usd|eur|gbp|chf|jpy|cny|rub|krw|inr|brl|sek|dkk|nok|cad|aud|"
    r"swiss|us dollar|british pound|japanese yen|canadian dollar|australian dollar)"
    r"\s+(?:in(?:to)?|to|in)\s+"
    r"(dollars?|euros?|pounds?|francs?|yen|yuan|rubles?|won|rupees?|reais?|real|"
    r"krona|kronor|krone|usd|eur|gbp|chf|jpy|cny|rub|krw|inr|brl|sek|dkk|nok|cad|aud|"
    r"swiss|us dollar|british pound|japanese yen|canadian dollar|australian dollar)",
    re.I,
)

# "exchange rate USD to EUR"
_RATE_PATTERN = re.compile(
    r"(?:exchange\s+rate|wechselkurs)\s+"
    r"(usd|eur|gbp|chf|jpy|cny|rub|krw|inr|brl|sek|dkk|nok|cad|aud|dollars?|euros?|pounds?)"
    r"\s+(?:to|in)\s+"
    r"(usd|eur|gbp|chf|jpy|cny|rub|krw|inr|brl|sek|dkk|nok|cad|aud|dollars?|euros?|pounds?)",
    re.I,
)


def _normalize(code: str) -> str:
    return _ALIASES.get(code.lower().strip(), code.upper().strip())


def _fetch_rate(from_code: str, to_code: str, amount: float) -> dict:
    resp = http_get(
        "https://api.frankfurter.app/latest",
        params={"amount": amount, "from": from_code, "to": to_code},
    )
    resp.raise_for_status()
    return resp.json()


def run(args: dict | None = None) -> str:
    utterance = ((args or {}).get("utterance") or "").strip()
    language = (args or {}).get("language", "en")
    de = language == "de"

    # Rate query (no amount)
    m = _RATE_PATTERN.search(utterance)
    if m:
        from_code = _normalize(m.group(1))
        to_code = _normalize(m.group(2))
        try:
            data = _fetch_rate(from_code, to_code, 1.0)
            rate = data.get("rates", {}).get(to_code)
            if rate is None:
                return f"Kurs für {from_code}/{to_code} nicht verfügbar." if de else f"Rate for {from_code}/{to_code} not available."
            if de:
                return f"1 {from_code} = {rate:.4f} {to_code}."
            return f"1 {from_code} = {rate:.4f} {to_code}."
        except Exception as e:
            return f"Wechselkurs nicht abrufbar: {e}" if de else f"Couldn't fetch exchange rate: {e}"

    # Conversion with amount
    m = _PATTERN.search(utterance)
    if m:
        amount_str = m.group(1).replace(",", ".")
        from_code = _normalize(m.group(2))
        to_code = _normalize(m.group(3))
        try:
            amount = float(amount_str)
            data = _fetch_rate(from_code, to_code, amount)
            converted = data.get("rates", {}).get(to_code)
            if converted is None:
                return f"Konvertierung {from_code}→{to_code} nicht verfügbar." if de else f"Conversion {from_code}→{to_code} not available."
            if de:
                return f"{amount:g} {from_code} = {converted:.2f} {to_code}."
            return f"{amount:g} {from_code} = {converted:.2f} {to_code}."
        except Exception as e:
            return f"Konvertierung fehlgeschlagen: {e}" if de else f"Conversion failed: {e}"

    return (
        "Sag z.B. '100 Dollar in Euro' oder 'Wechselkurs EUR zu GBP'."
        if de
        else "Try: 'convert 100 USD to EUR' or 'exchange rate GBP to USD'."
    )


def self_test() -> bool:
    return isinstance(META.get("triggers"), list) and callable(run)
