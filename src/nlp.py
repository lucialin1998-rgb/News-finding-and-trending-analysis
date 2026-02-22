from __future__ import annotations

import logging
import re
from collections import Counter
from typing import Dict, List, Tuple

from .utils import Article

LOGGER = logging.getLogger(__name__)

COMPANY_HINTS = {
    "universal music group", "sony music", "warner music", "spotify", "apple music", "live nation", "ticketmaster"
}
STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "for", "to", "in", "on", "with", "by", "from", "at", "is", "are", "this", "that",
    "music", "news", "week", "said", "says"
}


def load_spacy_model():
    try:
        import spacy

        return spacy.load("en_core_web_sm")
    except Exception:
        LOGGER.warning("spaCy model unavailable. Using rule-based entity extraction.")
        return None


def summarize_article(article: Article, max_bullets: int = 3) -> List[str]:
    text = (article.text_for_nlp or f"{article.title_en}. {article.excerpt_en}").strip()
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.strip()) > 35]
    if not sentences:
        sentences = [f"{article.title_en}. {article.excerpt_en}"]
    freq = Counter(_tokenize(text))
    scored = []
    for sent in sentences:
        words = _tokenize(sent)
        if not words:
            continue
        score = sum(freq[w] for w in words) / len(words)
        scored.append((score, sent))
    top = [s for _, s in sorted(scored, key=lambda x: x[0], reverse=True)[:max_bullets]]
    return [f"- {t[:220]}" for t in top if t]


def extract_entities(article: Article, nlp=None) -> List[dict]:
    text = f"{article.title_en}. {article.excerpt_en}. {article.text_for_nlp[:1500]}"
    entities = []
    if nlp is not None:
        doc = nlp(text)
        for ent in doc.ents:
            entities.append({"entity_en": ent.text.strip(), "category": _map_label(ent.text, ent.label_)})
    else:
        for term in re.findall(r"\b([A-Z][A-Za-z&.-]+(?:\s+[A-Z][A-Za-z&.-]+){0,4})\b", text):
            entities.append({"entity_en": term.strip(), "category": _map_label(term, "")})

    uniq = {}
    for item in entities:
        key = item["entity_en"].lower()
        if key not in uniq:
            uniq[key] = item
    return list(uniq.values())


def aggregate_entity_frequency(entities_by_article: Dict[str, List[dict]]) -> List[Tuple[str, str, int]]:
    counts = Counter()
    categories = {}
    for entities in entities_by_article.values():
        for entity in entities:
            name = entity["entity_en"]
            counts[name] += 1
            categories[name] = entity["category"]
    return [(name, categories.get(name, "Other"), count) for name, count in counts.most_common()]


def extract_trends(articles: List[Article]) -> List[str]:
    if not articles:
        return ["- Insufficient evidence: no articles collected."]
    corpus = [f"{a.title_en}. {a.excerpt_en}. {' '.join(a.summary_en)}" for a in articles]
    tokens = Counter()
    for text in corpus:
        tokens.update(_tokenize(text))

    trends = []
    for term, _ in tokens.most_common(20):
        matched = []
        for article in articles:
            merged = f"{article.title_en} {article.excerpt_en} {' '.join(article.summary_en)}".lower()
            if term in merged:
                matched.append(article)
        if len(matched) < 2:
            continue
        refs = "; ".join(f"{m.title_en} ({m.source}, {m.date[:10] if m.date else 'date unknown'})" for m in matched[:5])
        trends.append(f"- Theme: **{term}** appears repeatedly. Evidence: {refs}.")
        if len(trends) >= 8:
            break
    if not trends:
        trends.append("- Insufficient evidence to detect recurring themes.")
    return trends


def _tokenize(text: str) -> List[str]:
    return [w for w in re.findall(r"[A-Za-z][A-Za-z\-']+", text.lower()) if w not in STOPWORDS and len(w) > 2]


def _map_label(entity: str, ner_label: str) -> str:
    low = entity.lower()
    if low in COMPANY_HINTS or any(x in low for x in ["music", "records", "group", "media", "entertainment"]):
        return "Company"
    if ner_label == "PERSON":
        return "Artist/Person"
    if ner_label == "ORG":
        return "Organization"
    if ner_label in {"GPE", "LOC"}:
        return "Place"
    return "Other"
