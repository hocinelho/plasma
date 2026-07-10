# Skills Reference

Plasma includes 29 built-in skills that respond to voice commands. Skills are matched by keyword triggers -- the longest matching trigger wins.

## Skill List

| # | Skill | Description | Triggers |
|---|-------|-------------|----------|
| 1 | `get_time` | Returns the current local time | "what time", "what's the time", "current time", "time is it", "tell me the time", "wie spat ist es", "uhrzeit" |
| 2 | `get_date` | Returns today's date | "what's the date", "what date", "today's date", "what day is it", "welches datum", "welcher tag ist heute" |
| 3 | `weather` | Returns current weather for a city | "weather", "what's the weather", "weather in", "weather today", "wie ist das wetter", "wetter heute" |
| 4 | `weather_forecast` | Returns a 5-day weather forecast | "weather forecast", "5 day forecast", "weather this week", "weather tomorrow", "forecast for" |
| 5 | `calculator` | Evaluates math expressions | "calculate", "compute", "what is", "how much is", "plus", "minus", "times", "divided by", "rechne", "berechne" |
| 6 | `unit_converter` | Converts between units | "convert", "how many", "in kilometers", "in miles", "in celsius", "in fahrenheit", "to kg", "to pounds" |
| 7 | `timer` | Sets a countdown timer | "set a timer", "timer for", "countdown for", "stell einen timer", "timer fur" |
| 8 | `reminder` | Sets a time-based reminder | "remind me", "set a reminder", "don't let me forget", "alert me", "notify me" |
| 9 | `joke` | Tells a random joke | "tell me a joke", "make me laugh", "joke", "erzahl mir einen witz", "witz" |
| 10 | `wikipedia_lookup` | Wikipedia summary for a topic | "who is", "who was", "tell me about", "look up", "wikipedia" |
| 11 | `translator` | Translates words/phrases | "translate", "how do you say", "say ... in french/spanish/german" |
| 12 | `open_app` | Opens Windows apps or websites | "open ...", "launch ...", "start ..." |
| 13 | `volume` | Controls system volume | "volume up", "volume down", "louder", "quieter", "mute", "unmute" |
| 14 | `screenshot` | Takes a screenshot | "take a screenshot", "capture the screen", "screen capture" |
| 15 | `spotify_control` | Controls Spotify playback | "play music", "pause music", "next song", "what's playing", "skip track" |
| 16 | `calendar_today` | Reads Outlook calendar events | "what's on my calendar", "my schedule today", "any meetings today" |
| 17 | `calendar_add` | Creates Outlook calendar events | "add to my calendar", "schedule a meeting", "create an event" |
| 18 | `email_count` | Checks unread Outlook emails | "check my email", "any new emails", "how many unread", "my inbox" |
| 19 | `voice_notes` | Saves and reads voice notes | "take a note", "write this down", "read my notes", "show my notes" |
| 20 | `todo_list` | Manages a todo list | "add to my list", "my todo list", "show my list", "mark as done" |
| 21 | `news_disclaimer` | Fetches BBC News headlines | "what's the news", "any news", "news today", "top headlines" |
| 22 | `remember_this` | Stores a fact about you | "remember that", "remember my", "don't forget that" |
| 23 | `what_do_you_remember` | Reads back stored facts | "what do you remember", "what do you know about me" |
| 24 | `forget_this` | Deletes a stored fact | "forget that", "forget about", "delete fact" |
| 25 | `voice_select` | Switches TTS voice | "switch voice to", "list voices", "available voices", "stimme wechseln" |
| 26 | `who_am_i` | Identifies the speaker | "who am i", "do you recognize me", "wer bin ich" |
| 27 | `settings_control` | Changes runtime settings | "switch to faster model", "speak german", "what model", "auto detect language" |
| 28 | `update_check` | Checks for Plasma updates | "check for updates", "plasma version", "what version" |
| 29 | `list_proposals` | Lists pending skill proposals | "show proposals", "list proposals", "any new skills" |

## Adding Custom Skills

Create a Python file in `backend/skills/` with this structure:

```python
META = {
    "name": "my_skill",
    "description": "What this skill does.",
    "triggers": ["trigger phrase 1", "trigger phrase 2"],
    "example_utterances": ["Example: trigger phrase 1"],
}

def run(args: dict | None = None) -> str:
    utterance = (args or {}).get("utterance", "")
    language = (args or {}).get("language", "en")
    return "Skill response text."

def self_test() -> bool:
    return True
```

The skill is auto-discovered on startup. The `run()` function receives:

| Key | Type | Description |
|-----|------|-------------|
| `utterance` | `str` | The user's spoken text |
| `session_id` | `str` | Current session identifier |
| `language` | `str` | Detected language code (`en`, `de`, etc.) |
| `speaker` | `str` or `None` | Identified speaker name |
