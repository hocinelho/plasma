"""Skill: news_disclaimer — explains Plasma can't fetch live news yet."""
from __future__ import annotations


META = {
    "name": "news_disclaimer",
    "description": "Politely declines news/current-events questions.",
    "triggers": [
        "what's the news",
        "what is the news",
        "any news",
        "news today",
        "what is happening",
        "what's happening in the world",
        "what war",
        "current events",
        "latest news",
    ],
}


def run(args=None):
    return (
        "I don't have access to live news or the internet yet. "
        "I'll get that capability when we add cloud LLM support in step 9."
    )


def self_test():
    return "live news" in run().lower()
