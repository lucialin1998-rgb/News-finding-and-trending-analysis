from __future__ import annotations

import logging
import re
from collections import Counter, defaultdict
from typing import Dict, List, Tuple

from .utils import Article

LOGGER = logging.getLogger(__name__)

COMPANY_HINTS = {
    "universal music group",
    "sony music",
    "warner music",
    "spotify",
    "apple music",
    "live nation",
    "ticketmaster",
    "tiktok",
    "youtube",
    "amazon music",
}

STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "for", "to", "in", "on", "with", "by", "from", "at", "is",
    "are", "as", "that", "this", "it", "its", "be", "has", "have", "after", "new", "music", "week",
}


def load_spacy_model():
    try:
        import spacy

        return spacy.load("en_core_web_sm")
    except Exception:
        LOGGER.warning(
            "spaCy model en_core_web_sm is not available. Falling back to simple rule-based entity extraction."
        )
        return None


def summarize_article(article: Article, max_bullets: int = 3) -> List[str]:
    text = article.text_for_nlp.strip() or f"{article.title}. {article.excerpt}"
    sentences = re.split(r"(?<=[.!?])\s+", text)
    clean_sentences = [s.strip() for s in sentences if len(s.strip()) > 30]
    if not clean_sentences:
        clean_sentences = [article.title, article.excerpt]

    word_freq = Counter(_tokenize(text))
    ranked = []
    for sentence in clean_sentences:
        tokens = _tokenize(sentence)
        if not tokens:
            continue
        score = sum(word_freq[t] for t in tokens) / len(tokens)
        ranked.append((score, sentence))

    top = [s for _, s in sorted(ranked, key=lambda x: x[0], reverse=True)[:max_bullets]]
    if not top:
        top = [article.title, article.excerpt]
    return [f"- {s[:220]}" for s in top[:max_bullets] if s]


def extract_entities(article: Article, nlp=None) -> List[dict]:
    text = f"{article.title}. {article.excerpt}. {article.text_for_nlp[:2000]}"
    entities = []

    if nlp is not None:
        doc = nlp(text)
        for ent in doc.ents:
            label = _classify_entity(ent.text, ent.label_)
            entities.append({"entity": ent.text.strip(), "category": label})
    else:
        candidates = re.findall(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-zA-Z&.-]+){0,4})\b", text)
        for item in candidates:
            label = _classify_entity(item, "UNKNOWN")
            entities.append({"entity": item.strip(), "category": label})

    deduped = {}
    for e in entities:
        key = e["entity"].lower()
        if key not in deduped:
            deduped[key] = e
    return list(deduped.values())


def _classify_entity(entity_text: str, ner_label: str) -> str:
    low = entity_text.lower()
    if low in COMPANY_HINTS:
        return "Company"
    if ner_label == "PERSON":
        return "Artist/Person"
    if ner_label == "ORG":
        return "Company" if any(word in low for word in ["music", "records", "group", "entertainment", "media"]) else "Organization"
    if ner_label in {"GPE", "LOC"}:
        return "Place"
    if any(token in low for token in ["music", "records", "group", "ltd", "inc", "plc"]):
        return "Company"
    return "Other"


def aggregate_entity_frequency(entities_by_article: Dict[str, List[dict]]) -> List[Tuple[str, str, int]]:
    counter = Counter()
    category_map = {}
    for entities in entities_by_article.values():
        for entity in entities:
            key = entity["entity"].strip()
            counter[key] += 1
            category_map[key] = entity["category"]
    ranked = [(name, category_map.get(name, "Other"), count) for name, count in counter.most_common()]
    return ranked


def extract_trends(articles: List[Article]) -> List[str]:
    if not articles:
        return ["- Insufficient evidence: no articles were collected for the selected date range."]

    corpus = [f"{a.title}. {a.excerpt}. {' '.join(a.summary_bullets)}" for a in articles]
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer

        vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), max_features=80)
        matrix = vec.fit_transform(corpus)
        terms = vec.get_feature_names_out()
        scores = matrix.sum(axis=0).A1
        ranked_terms = [terms[i] for i in scores.argsort()[::-1] if len(terms[i]) > 3][:12]
    except Exception:
        all_tokens = Counter()
        for text in corpus:
            all_tokens.update(_tokenize(text))
        ranked_terms = [tok for tok, _ in all_tokens.most_common(12)]

    trends = []
    for term in ranked_terms[:8]:
        matching = []
        for a in articles:
            joined = f"{a.title} {a.excerpt} {' '.join(a.summary_bullets)}".lower()
            if term.lower() in joined:
                matching.append(a)
        if len(matching) < 2:
            continue
        refs = "; ".join(f"{m.title} ({m.source}, {m.date_iso[:10]})" for m in matching[:4])
        trends.append(f"- Theme: **{term}** appears repeatedly. Evidence: {refs}.")

    if not trends:
        trends.append("- Insufficient evidence to identify repeated themes with confidence.")
    return trends[:10]


def _tokenize(text: str) -> List[str]:
    tokens = re.findall(r"[A-Za-z][A-Za-z\-']+", text.lower())
    return [t for t in tokens if t not in STOPWORDS and len(t) > 2]
