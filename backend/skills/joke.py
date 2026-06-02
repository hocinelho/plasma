"""PA-55 — Joke skill: "tell me a joke"."""
from __future__ import annotations
import random

META = {
    "name": "joke",
    "description": "Tells a random short joke.",
    "triggers": [
        "tell me a joke",
        "say a joke",
        "give me a joke",
        "make me laugh",
        "tell a joke",
        "joke",
    ],
}

_JOKES = [
    "Why don't scientists trust atoms? Because they make up everything.",
    "I told my wife she was drawing her eyebrows too high. She looked surprised.",
    "What do you call a fake noodle? An impasta.",
    "Why did the scarecrow win an award? He was outstanding in his field.",
    "I'm reading a book about anti-gravity. It's impossible to put down.",
    "What do you call cheese that isn't yours? Nacho cheese.",
    "Why can't you give Elsa a balloon? Because she'll let it go.",
    "I used to hate facial hair, but then it grew on me.",
    "What do you call a sleeping dinosaur? A dino-snore.",
    "Why did the bicycle fall over? Because it was two-tired.",
    "What do you call a bear with no teeth? A gummy bear.",
    "I only know 25 letters of the alphabet. I don't know why.",
    "What do you call a fish without eyes? A fsh.",
    "Why do cows wear bells? Because their horns don't work.",
    "I asked my dog what two minus two is. He said nothing.",
]


def run(args: dict | None = None) -> str:
    return random.choice(_JOKES)


def self_test() -> bool:
    return isinstance(run({}), str) and len(run({})) > 10
