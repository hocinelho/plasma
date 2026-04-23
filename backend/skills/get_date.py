"""Returns today's date."""
from datetime import datetime

META = {
    "name": "get_date",
    "description": "Returns today's date.",
    "triggers": ["what's the date", "what date", "today's date", "what day is it"],
}

def run(args=None):
    return datetime.now().strftime("Today is %A, %B %d, %Y.")

def self_test():
    return "Today is" in run()