"""Menura retrieval engine.

A question is answered in stages, from strict to forgiving:

1. Word match on topics: Turkish preprocessing (tokenizing, stopword removal,
   Snowball stemming) + TF-IDF + cosine similarity against each topic's
   user_input and tags.
2. Word match on products: the same, against every product listed in a topic.
3. Fuzzy match: character n-gram TF-IDF on text with Turkish letters folded
   (ç→c, ş→s, ı→i ...), so typos and spelling variants such as "magnolya",
   "kapuçino" or "cay" still find "Magnolia", "Cappuccino" and "Bardak Çay".
4. Fallback.
"""

from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass, replace
from pathlib import Path

import nltk
import numpy as np
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from snowballstemmer import stemmer as snowball_stemmer

DEFAULT_DATA = Path(__file__).resolve().parent.parent / "data" / "menu.json"

_NLTK_RESOURCES = {
    "tokenizers/punkt": "punkt",
    "tokenizers/punkt_tab": "punkt_tab",
    "corpora/stopwords": "stopwords",
}

# Words that carry no menu meaning in questions like "latte var mı?" or "bir tane çay istiyorum".
EXTRA_STOPWORDS = {
    "var", "yok", "mı", "mi", "mu", "mü", "mısınız", "misiniz", "musunuz", "istiyorum", "isterim",
    "lütfen", "bir", "tane", "acaba", "bana", "alabilir", "alabilirmiyim", "miyim", "olur",
    "verir", "getirir", "getirebilir",
}

# NLTK stopwords that carry meaning here ("neler var?" asks for the menu).
KEEP_WORDS = {"neler"}

_FOLD = str.maketrans("çğıöşüâîû", "cgiosuaiu")


def ensure_nltk_data() -> None:
    """Download the NLTK resources Menura needs, only if they are missing."""
    for resource, package in _NLTK_RESOURCES.items():
        try:
            nltk.data.find(resource)
        except LookupError:
            nltk.download(package, quiet=True)


def turkish_lower(text: str) -> str:
    """Lowercase with Turkish dotted/dotless I rules."""
    return text.replace("İ", "i").replace("I", "ı").lower()


@dataclass(frozen=True)
class Reply:
    """A bot answer plus how it was found, so interfaces can explain the match."""

    text: str
    kind: str  # "topic", "item", "option" or "fallback"
    score: float
    topic: str | None = None
    item: str | None = None
    fuzzy: bool = False
    option: str | None = None  # e.g. "şekersiz" when the guest asked for an option


def extract_items(response: str) -> list[str]:
    """Return the product names listed in a category response."""
    items = []
    for line in response.splitlines():
        line = line.strip()
        if not line or line.startswith(("★", "【")) or line.endswith(":"):
            continue
        items.append(line.removeprefix("- ").strip())
    return items


class MenuraBot:
    """Retrieval-based Turkish menu assistant."""

    name = "Menura"

    def __init__(self, data_file: str | Path = DEFAULT_DATA, *,
                 topic_threshold: float = 0.25, item_threshold: float = 0.5,
                 fuzzy_item_threshold: float = 0.55, fuzzy_topic_threshold: float = 0.75,
                 seed: int | None = None) -> None:
        ensure_nltk_data()
        self._stemmer = snowball_stemmer("turkish")
        self._stop_words = (set(stopwords.words("turkish")) | EXTRA_STOPWORDS) - KEEP_WORDS
        self._rng = random.Random(seed)
        self.topic_threshold = topic_threshold
        self.item_threshold = item_threshold
        self.fuzzy_item_threshold = fuzzy_item_threshold
        self.fuzzy_topic_threshold = fuzzy_topic_threshold

        data = json.loads(Path(data_file).read_text(encoding="utf-8"))
        self._welcome = data["welcome"]
        self._fallback = data["fallback"]
        self.entries: list[dict] = data["entries"]
        self._by_topic = {e["user_input"]: e for e in self.entries}
        self.categories = [e["user_input"] for e in self.entries if e.get("index_items", True)]
        # Option rules ("şekersiz", "sütsüz" ...): each pattern matches a word start, with
        # Turkish letters folded, so "şekersizi" and "sekersiz" both count. A pattern that
        # starts with "=" must match a whole word ("=ice" must not match "içecek").
        self._modifiers = [(modifier, self._option_regex(modifier["patterns"]))
                           for modifier in data.get("modifiers", [])]

        # Each topic name and each tag is indexed as its own phrase, so adding synonyms
        # never dilutes the others; a phrase match points back to its entry.
        self._phrases: list[tuple[int, str]] = [
            (index, phrase)
            for index, entry in enumerate(self.entries)
            for phrase in [entry["user_input"], *entry.get("tags", [])]
        ]
        topic_texts = [phrase for _, phrase in self._phrases]
        self._items: list[tuple[int, str]] = [
            (index, item)
            for index, entry in enumerate(self.entries)
            if entry.get("index_items", True) and isinstance(entry["bot_response"], str)
            for item in extract_items(entry["bot_response"])
        ]
        item_texts = [item for _, item in self._items]

        self._topic_words = self._index(TfidfVectorizer(), [self.preprocess(t) for t in topic_texts])
        self._item_words = self._index(TfidfVectorizer(), [self.preprocess(t) for t in item_texts])
        self._topic_chars = self._index(self._char_vectorizer(), [self.fold(t) for t in topic_texts])
        self._item_chars = self._index(self._char_vectorizer(), [self.fold(t) for t in item_texts])

    # ---------- text processing ----------

    def _words(self, text: str) -> list[str]:
        # Split hyphenated names ("Coca-Cola") and keep only letters and digits inside each
        # token, so punctuation and invisible characters (e.g. a BOM) do not hide a word.
        tokens = word_tokenize(turkish_lower(text).replace("-", " "), language="turkish")
        cleaned = ("".join(ch for ch in t if ch.isalnum()) for t in tokens)
        return [t for t in cleaned if t and t not in self._stop_words]

    def preprocess(self, text: str) -> str:
        """Tokenize, drop stopwords and stem each token (used for word matching)."""
        return " ".join(self._stem(t) for t in self._words(text))

    def _stem(self, token: str) -> str:
        # Snowball over-stems some short words ("kimsin" -> "k", "iyiyim" -> "i"); a stem that
        # short carries no meaning and TF-IDF ignores it, so keep the original word instead.
        stem = self._stemmer.stemWord(token)
        return stem if len(stem) >= 3 else token

    def fold(self, text: str) -> str:
        """Drop stopwords and fold Turkish letters to ASCII (used for fuzzy matching)."""
        return " ".join(self._words(text)).translate(_FOLD)

    @staticmethod
    def _option_regex(patterns: list[str]) -> re.Pattern:
        parts = []
        for pattern in patterns:
            exact = pattern.startswith("=")
            body = re.escape(turkish_lower(pattern.lstrip("=")).translate(_FOLD))
            parts.append(body + (r"(?!\w)" if exact else r"\w*"))
        return re.compile(r"(?<!\w)(?:" + "|".join(parts) + ")")

    @staticmethod
    def _char_vectorizer() -> TfidfVectorizer:
        return TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4))

    @staticmethod
    def _index(vectorizer: TfidfVectorizer, docs: list[str]):
        return vectorizer, vectorizer.fit_transform(docs)

    @staticmethod
    def _best(index, query: str) -> tuple[int, float]:
        vectorizer, matrix = index
        scores = cosine_similarity(vectorizer.transform([query]), matrix)[0]
        best = int(np.argmax(scores))
        return best, float(scores[best])

    @classmethod
    def _best_covered(cls, index, query: str) -> tuple[int, float]:
        """Best word match, scaled by the share of query words the index knows.

        TF-IDF silently ignores unknown words, so without this "ice latte" would
        score 1.0 against any phrase that only contains "iç".
        """
        best, score = cls._best(index, query)
        tokens = query.split()
        vocabulary = index[0].vocabulary_
        coverage = sum(token in vocabulary for token in tokens) / len(tokens)
        return best, score * coverage

    # ---------- answers ----------

    def _pick(self, value):
        """Entries may hold one answer or a list of alternatives."""
        return self._rng.choice(value) if isinstance(value, list) else value

    @property
    def welcome(self) -> str:
        return self._pick(self._welcome)

    @property
    def fallback(self) -> str:
        return self._pick(self._fallback)

    def _topic_reply(self, phrase_index: int, score: float, fuzzy: bool = False) -> Reply:
        entry = self.entries[self._phrases[phrase_index][0]]
        if entry.get("action") == "recommend":
            text = self._recommend(entry)
        else:
            text = self._pick(entry["bot_response"])
        return Reply(text, "topic", score, topic=entry["user_input"], fuzzy=fuzzy)

    def _item_reply(self, index: int, score: float, query: str, fuzzy: bool = False) -> Reply:
        entry_index, item = self._items[index]
        entry = self.entries[entry_index]
        # Only claim "Evet, ... var" for a near-exact match; partial ones are labelled as such.
        fuzzy = fuzzy or score < 0.9
        if fuzzy:
            intro = f"“{query}” için en yakın sonuç: {item}. {entry['user_input']} listemiz aşağıda."
        else:
            intro = f"Evet, {item} menümüzde var. {entry['user_input']} listemiz aşağıda."
        return Reply(intro + entry["bot_response"], "item", score,
                     topic=entry["user_input"], item=item, fuzzy=fuzzy)

    def _recommend(self, entry: dict) -> str:
        picks = []
        for topic in entry["recommend_from"]:
            items = extract_items(self._by_topic[topic]["bot_response"])
            picks.append(self._rng.choice(items))
        return self._pick(entry["bot_response"]).format(*picks)

    def _detect_option(self, text: str) -> tuple[dict | None, str]:
        """Find an option such as "şekersiz" and return it with the rest of the message."""
        lowered = turkish_lower(text)
        folded = lowered.translate(_FOLD)  # one-to-one, so indices line up with `lowered`
        for modifier, pattern in self._modifiers:
            found = pattern.search(folded)
            if found:
                return modifier, f"{lowered[:found.start()]} {lowered[found.end():]}".strip()
        return None, text

    def reply(self, text: str, last_topic: str | None = None) -> Reply:
        """Answer a user message.

        `last_topic` is the menu category of the previous answer, so a follow-up such as
        "şekersiz mi peki?" after the coffee list is answered for coffees.
        """
        modifier, rest = self._detect_option(text)
        if modifier is None:
            return self._match(text)

        base = self._match(rest)
        on_menu = base.kind in ("topic", "item") and base.topic in self.categories
        topic = base.topic if on_menu else (last_topic if last_topic in self.categories else None)
        note = modifier["notes"].get(topic, modifier["default"]) if topic else modifier["default"]
        if on_menu:
            joiner = "" if base.text.startswith("\n") else " "
            return replace(base, text=note + joiner + base.text, option=modifier["name"])
        return Reply(note, "option", 1.0, topic=topic, option=modifier["name"])

    def _match(self, text: str) -> Reply:
        """Match a message against topics and products (no option handling)."""
        words = self.preprocess(text)
        if not words:
            return Reply(self.fallback, "fallback", 0.0)

        topic_i, topic_s = self._best_covered(self._topic_words, words)
        item_i, item_s = self._best_covered(self._item_words, words)
        # A product is more specific than a topic, so it wins ties.
        if item_s >= self.item_threshold and item_s >= topic_s:
            return self._item_reply(item_i, item_s, text)
        if topic_s >= self.topic_threshold:
            return self._topic_reply(topic_i, topic_s)
        if item_s >= self.item_threshold:
            return self._item_reply(item_i, item_s, text)

        folded = self.fold(text)
        fitem_i, fitem_s = self._best(self._item_chars, folded)
        ftopic_i, ftopic_s = self._best(self._topic_chars, folded)
        if ftopic_s >= self.fuzzy_topic_threshold and ftopic_s >= fitem_s:
            return self._topic_reply(ftopic_i, ftopic_s, fuzzy=True)
        if fitem_s >= self.fuzzy_item_threshold:
            return self._item_reply(fitem_i, fitem_s, text.strip(), fuzzy=True)

        return Reply(self.fallback, "fallback", max(topic_s, item_s, fitem_s, ftopic_s))

    def get_response(self, text: str) -> str:
        """Backward-compatible helper that returns only the answer text."""
        return self.reply(text).text
