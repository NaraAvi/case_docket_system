"""Statutory triage: deterministic detection of IPID Act s28(1) matters.

Pure functions only. The detector splits text into sentences and looks for an
offence pattern from ``corpus.S28_CATEGORIES``. Unless the category is
``standalone`` (already implies police involvement, e.g. "died in custody") the
offence must sit in the same sentence as a police actor, or in the sentence
directly after one that names the actor when it refers back with a pronoun
("The officer took me aside. He demanded a bribe."). Denials and hypotheticals
("he did not demand a bribe", "if an officer asks for money") are ignored.
"""

from __future__ import annotations

import re
from functools import lru_cache

from app.modules.regulatory_engine import corpus

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
_WORD = re.compile(r"[a-z']+")


@lru_cache(maxsize=1)
def _compiled():
    actor = re.compile(corpus.POLICE_ACTOR_PATTERN, re.IGNORECASE)
    pronoun = re.compile(corpus.PRONOUN_PATTERN, re.IGNORECASE)
    categories = {}
    for code, category in corpus.S28_CATEGORIES.items():
        categories[code] = (
            category,
            [re.compile(pattern, re.IGNORECASE) for pattern in category.get("patterns", [])],
            [re.compile(pattern, re.IGNORECASE) for pattern in category.get("context_patterns", [])],
        )
    return actor, pronoun, categories


def normalise(text):
    return str(text or "").replace("’", "'").replace("‘", "'").strip()


def split_sentences(text):
    return [part.strip() for part in _SENTENCE_SPLIT.split(normalise(text)) if part and part.strip()]


def _is_negated(sentence, start):
    words = _WORD.findall(sentence[:start].lower())[-corpus.NEGATION_WINDOW_WORDS:]
    return any(word in corpus.NEGATORS for word in words)


def _first_affirmed_match(patterns, sentence):
    for pattern in patterns:
        for match in pattern.finditer(sentence):
            if not _is_negated(sentence, match.start()):
                return match
    return None


def collect_text_sources(docket_data, extra_texts=None):
    """Flatten a docket (plus any extra free text) into ordered
    ``(label, text)`` pairs. Order is fixed so results are reproducible."""
    docket = docket_data or {}
    sources = []
    if docket.get("title"):
        sources.append(("title", docket["title"]))
    if docket.get("description"):
        sources.append(("description", docket["description"]))
    for index, statement in enumerate(docket.get("statements") or [], start=1):
        if isinstance(statement, dict):
            text = statement.get("statement_text") or statement.get("statement_content")
        else:
            text = statement
        if text:
            sources.append((f"statement[{index}]", text))
    for index, item in enumerate(docket.get("evidence") or [], start=1):
        if isinstance(item, dict) and item.get("description"):
            sources.append((f"evidence[{index}]", item["description"]))
    for index, flag in enumerate(docket.get("flags") or [], start=1):
        if isinstance(flag, dict) and flag.get("notes"):
            sources.append((f"flag[{index}]", flag["notes"]))
    if isinstance(extra_texts, dict):
        extra_texts = list(extra_texts.items())
    for label, text in extra_texts or []:
        if text:
            sources.append((str(label), text))
    return sources


def detect_statutory_matters(sources):
    """Return the ordered list of s28(1) categories triggered by ``sources``.

    Each result is ``{"rule_code", "matches": [{"source", "matched_text",
    "sentence"}]}`` in corpus order, one entry per category.
    """
    actor, pronoun, categories = _compiled()
    found = {}
    for label, text in sources:
        sentences = split_sentences(text)
        for index, sentence in enumerate(sentences):
            for code, (category, patterns, contexts) in categories.items():
                if not category.get("auto_detect"):
                    continue
                match = _first_affirmed_match(patterns, sentence)
                if match is None:
                    continue
                if contexts and not all(context.search(sentence) for context in contexts):
                    continue
                if category.get("requires_police_actor"):
                    actor_here = actor.search(sentence) is not None
                    actor_before = index > 0 and actor.search(sentences[index - 1]) is not None and pronoun.search(sentence) is not None
                    if not (actor_here or actor_before):
                        continue
                found.setdefault(code, []).append(
                    {"source": label, "matched_text": match.group(0), "sentence": sentence}
                )
    return [{"rule_code": code, "matches": found[code]} for code in corpus.S28_CATEGORIES if code in found]
