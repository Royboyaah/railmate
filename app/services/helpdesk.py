"""Help desk: TF-IDF retrieval over a curated FAQ (no external AI service)."""

from __future__ import annotations

import json
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel

MIN_SIMILARITY = 0.12


class HelpDesk:
    def __init__(self, faq_path: Path):
        self.items: list[dict] = json.loads(faq_path.read_text(encoding="utf-8"))
        corpus = [f"{i['q']} {i['tags']} {i['tags']} {i['a']}" for i in self.items]
        # word n-grams for meaning + character n-grams for typos ("tatkaal", "lugage")
        self.word = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, stop_words="english")
        self.char = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 4), sublinear_tf=True)
        self.word_m = self.word.fit_transform(corpus)
        self.char_m = self.char.fit_transform(corpus)

    def topics(self) -> list[str]:
        return [i["q"] for i in self.items]

    def answer(self, question: str) -> dict:
        q = question.strip()[:300]
        if not q:
            return {"matched": False, "answer": "Please type a question.", "related": []}
        sims = (0.6 * linear_kernel(self.word.transform([q]), self.word_m)[0]
                + 0.4 * linear_kernel(self.char.transform([q]), self.char_m)[0])
        order = sims.argsort()[::-1]
        best = int(order[0])
        if sims[best] < MIN_SIMILARITY:
            return {
                "matched": False,
                "answer": "I'm not sure about that one. Try asking about PNR, Tatkal, cancellations, "
                          "classes, fares, delay risk or how RailMate ranks journeys.",
                "related": [self.items[int(i)]["q"] for i in order[:3]],
            }
        return {
            "matched": True,
            "question": self.items[best]["q"],
            "answer": self.items[best]["a"],
            "confidence": round(float(sims[best]), 2),
            "related": [self.items[int(i)]["q"] for i in order[1:4] if sims[int(i)] >= MIN_SIMILARITY],
        }
