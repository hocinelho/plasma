"""PA-54 — Calculator skill: "what is 12 times 34" / "calculate 100 divided by 4"."""
from __future__ import annotations
import re

META = {
    "name": "calculator",
    "description": "Evaluates simple math expressions spoken in natural language.",
    "triggers": [
        "calculate ",
        "compute ",
        "what is ",
        "how much is ",
        "what's ",
        "math ",
        "plus",
        "minus",
        "times",
        "divided by",
        "multiplied by",
        "rechne ",
        "berechne ",
        "was ist ",
        "wie viel ist ",
    ],
}

_WORD_OPS = [
    (re.compile(r"\btimes\b|\bmultiplied by\b", re.I), "*"),
    (re.compile(r"\bdivided by\b", re.I), "/"),
    (re.compile(r"\bplus\b|\band\b", re.I), "+"),
    (re.compile(r"\bminus\b", re.I), "-"),
    (re.compile(r"\bto the power of\b|\bto the\b", re.I), "**"),
    (re.compile(r"\bsquared\b", re.I), "**2"),
    (re.compile(r"\bcubed\b", re.I), "**3"),
]

_STRIP = re.compile(
    r"^(what\s*is|what's|calculate|compute|how\s*much\s*is|math)\s*",
    re.I,
)

_SAFE = re.compile(r"^[\d\s\+\-\*\/\(\)\.\%\*]+$")


def _to_expr(text: str) -> str:
    text = _STRIP.sub("", text).strip(" ?")
    for pattern, op in _WORD_OPS:
        text = pattern.sub(op, text)
    # remove leftover words
    text = re.sub(r"[a-zA-Z]+", "", text).strip()
    return text


def run(args: dict | None = None) -> str:
    utterance = (args or {}).get("utterance", "")
    expr = _to_expr(utterance)

    if not expr or not _SAFE.match(expr):
        return "I can only do basic math: addition, subtraction, multiplication, and division."

    try:
        result = eval(expr, {"__builtins__": {}})  # noqa: S307 — safe: _SAFE validated
    except ZeroDivisionError:
        return "Can't divide by zero."
    except Exception:
        return "I couldn't parse that math expression."

    if isinstance(result, float) and result == int(result):
        result = int(result)

    return f"{result}."


def self_test() -> bool:
    return run({"utterance": "what is 6 times 7"}) == "42."
