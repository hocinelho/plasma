"""Passive learning — notice what the user tells you, and remember it.

Until now Plasma only remembered things when explicitly told ("remember that
I like strong coffee"). This module watches ordinary conversation and pulls
out facts worth keeping, classifies them, and folds them into memory without
piling up near-duplicates.

Three parts:

1. **Extract** — an LLM pass over the user's turn returns candidate facts,
   each with a category. Runs in the background *after* the reply is sent, so
   it never adds latency to the conversation.
2. **Classify** — into a fixed set of categories, so memory can be browsed
   and the profile writer can group things sensibly.
3. **Merge** — before storing, look for a fact that already says the same
   thing. Near-duplicates are the failure mode of passive learning: without
   this you end up with "likes coffee", "likes strong coffee" and "enjoys
   Algerian coffee" as three separate facts. Similar facts replace the older
   one rather than adding to it.

Deduplication is deliberately *not* embedding-based: that would mean shipping
another model. Token overlap over normalised text is cheap and, for short
personal facts, works well.
"""
from __future__ import annotations

import json
import logging
import re

log = logging.getLogger("plasma.learner")

# Categories the extractor may use. Anything else is coerced to "other" so a
# creative model can't fragment memory into dozens of one-off buckets.
CATEGORIES = (
    "identity",     # name, role, where they live, languages
    "preference",   # likes, dislikes, habits
    "work",         # employer, projects, colleagues, tools
    "relationship", # family, friends, pets
    "schedule",     # recurring commitments, routines
    "health",       # dietary needs, conditions they mention
    "project",      # things they are building or working on
    "other",
)

# Facts shorter than this are noise ("ok", "yes please").
MIN_FACT_CHARS = 8
MAX_FACT_CHARS = 200
# Above this token overlap two facts are treated as the same thing.
DUPLICATE_THRESHOLD = 0.6

_PROMPT = """Extract durable facts about the user from their message.

A durable fact is something still true next week: their name, job, city,
preferences, relationships, projects, routines. NOT questions, NOT commands,
NOT small talk, NOT anything about you.

Return ONLY a JSON array. Each item: {"fact": "...", "category": "..."}
Category must be one of: %s

Write each fact as a short third-person statement ("Prefers strong coffee").
Return [] if the message contains nothing durable. Invent nothing.

MESSAGE: %s"""

_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "to", "of", "in", "on", "at",
    "for", "and", "or", "his", "her", "their", "they", "he", "she", "it", "with",
    "has", "have", "had", "does", "do", "likes", "like", "very", "really",
    "der", "die", "das", "ein", "eine", "ist", "sind", "und", "oder", "mit",
}


def _tokens(text: str) -> set[str]:
    """Meaningful lowercase words, for comparing two facts."""
    words = re.findall(r"[\w']+", (text or "").lower())
    return {w for w in words if len(w) > 2 and w not in _STOPWORDS}


def similarity(a: str, b: str) -> float:
    """How much two facts say the same thing (0..1).

    Plain word overlap is not enough on its own: "Works at Vodafone" and
    "Works at Vodafone as a field engineer" share every meaningful word of the
    shorter fact, yet score only 0.5 because the longer one drags the union up.
    So a fact whose words are entirely contained in another — the "same thing,
    said in more detail" case — counts as a full match.

    Containment is required to be *total*. Partial containment would merge
    genuinely different facts that happen to share a couple of words, e.g.
    "Works at Vodafone in Moers" and "Lives in Moers near the Vodafone office".
    Keeping two similar facts is a much smaller loss than deleting a real one.
    """
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    overlap = len(ta & tb)
    jaccard = overlap / len(ta | tb)
    # One fact's words fully inside the other's, and not a bare single word
    # (a one-word fact would otherwise match anything mentioning that word).
    smaller = min(len(ta), len(tb))
    if smaller >= 2 and overlap == smaller:
        return 1.0
    return jaccard


def find_duplicate(fact: str, existing: list[dict]) -> dict | None:
    """The stored fact that already says this, if any."""
    best, best_score = None, 0.0
    for row in existing:
        score = similarity(fact, row.get("content", ""))
        if score > best_score:
            best, best_score = row, score
    return best if best_score >= DUPLICATE_THRESHOLD else None


def _clean(fact: str) -> str:
    fact = " ".join((fact or "").split()).strip(" .,;:")
    return fact[:MAX_FACT_CHARS]


def _parse(raw: str) -> list[dict]:
    """Pull the JSON array out of a model reply that may be wrapped in prose."""
    if not raw:
        return []
    fenced = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", raw, re.S)
    candidate = fenced.group(1) if fenced else None
    if candidate is None:
        start, end = raw.find("["), raw.rfind("]")
        if start == -1 or end <= start:
            return []
        candidate = raw[start : end + 1]
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []

    out = []
    for item in parsed:
        if isinstance(item, str):
            fact, category = item, "other"
        elif isinstance(item, dict):
            fact = str(item.get("fact", ""))
            category = str(item.get("category", "other")).lower().strip()
        else:
            continue
        fact = _clean(fact)
        if len(fact) < MIN_FACT_CHARS:
            continue
        out.append({
            "fact": fact,
            "category": category if category in CATEGORIES else "other",
        })
    return out


def extract_facts(message: str) -> list[dict]:
    """Candidate facts from one user message. [] if the model is unavailable."""
    message = (message or "").strip()
    if len(message) < MIN_FACT_CHARS:
        return []
    try:
        from backend.modules.router.chat_service import _llm_reply
        raw = _llm_reply(
            user_message=_PROMPT % (", ".join(CATEGORIES), message),
            history=[],
            system_prompt=(
                "You extract structured facts. You reply with a JSON array "
                "only — no preamble, no commentary, no code fences."
            ),
        )
    except Exception as e:
        log.debug("Fact extraction unavailable: %s", e)
        return []
    return _parse(raw)


def learn_from(message: str, speaker: str | None = None, memory=None) -> list[dict]:
    """Extract, deduplicate and store facts from one user message.

    Returns what was actually changed, e.g.
        [{"action": "added",   "fact": "...", "category": "work"},
         {"action": "updated", "fact": "...", "replaced": "..."},
         {"action": "skipped", "fact": "...", "duplicate_of": "..."}]
    """
    # Runs unattended in a background task: a failure here must never surface
    # as an unretrieved-exception warning, and must never lose the reply.
    try:
        candidates = extract_facts(message)
    except Exception as e:
        log.warning("Fact extraction failed: %s", e)
        return []
    if not candidates:
        return []

    if memory is None:
        from backend.modules.memory.store import MemoryStore
        memory = MemoryStore()

    existing = memory.get_facts(limit=500, user=speaker)
    results: list[dict] = []

    for item in candidates:
        fact, category = item["fact"], item["category"]
        dup = find_duplicate(fact, existing)

        if dup is None:
            memory.add_fact(category=category, content=fact,
                            source="learned", user=speaker)
            existing.append({"id": None, "content": fact, "category": category})
            results.append({"action": "added", "fact": fact, "category": category})
            continue

        # Same thing, said at more length → keep the richer version. Otherwise
        # leave memory alone; re-storing near-identical facts is what turns a
        # profile into noise.
        if len(fact) > len(dup.get("content", "")) + 10 and dup.get("id"):
            memory.delete_fact(dup["id"])
            memory.add_fact(category=category, content=fact,
                            source="learned", user=speaker)
            dup["content"] = fact
            results.append({"action": "updated", "fact": fact,
                            "replaced": dup.get("content", "")})
        else:
            results.append({"action": "skipped", "fact": fact,
                            "duplicate_of": dup.get("content", "")})

    added = sum(1 for r in results if r["action"] == "added")
    if added:
        log.info("Learned %d new fact(s) from the conversation", added)
    return results


def dedupe_existing(memory=None, user: str | None = None) -> int:
    """Collapse near-duplicates already sitting in memory. Returns count removed.

    Useful once, after turning passive learning on, to clean up whatever the
    old explicit-only flow accumulated.
    """
    if memory is None:
        from backend.modules.memory.store import MemoryStore
        memory = MemoryStore()

    facts = memory.get_facts(limit=1000, user=user)
    # Oldest first, so the newest phrasing is the one that survives.
    facts = sorted(facts, key=lambda f: f.get("id") or 0)
    kept: list[dict] = []
    removed = 0
    for row in facts:
        if find_duplicate(row.get("content", ""), kept):
            if row.get("id") and memory.delete_fact(row["id"]):
                removed += 1
            continue
        kept.append(row)
    if removed:
        log.info("Removed %d duplicate fact(s) from memory", removed)
    return removed
