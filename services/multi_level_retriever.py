# services/multi_level_retriever.py
"""
Multi-Level Retriever - 5-Level Search System (0-4)

Single keyword:
  Level 1: keyword + magic (strict phrase, slop=0)
  Level 2: synonym combinations
  Level 3: synonym + magic (strict phrase, slop=0)
  Level 4: semantic vector fallback

Multiple keywords:
  Level 0: keyword combinations
  Level 1: keyword + magic (each keyword with each magic word, slop=0)
  Level 2: synonym combinations (like Level 0 but with synonyms)
  Level 3: synonym + magic (strict phrase, slop=0)
  Level 4: semantic vector fallback
"""
from typing import List, Dict, Any, Set, Tuple, Optional
import logging
from services.embedder import get_embedding
from vector.elastic_client import es
from config import settings
from services.keyword_extractor import (
    generate_keyword_combinations,
    generate_synonyms,
    generate_keyword_magical_pairs,
    get_magical_words_for_level3,
)

logger = logging.getLogger(__name__)
INDEX = settings.ES_INDEX_NAME


class MultiLevelRetriever:
    def __init__(self, keywords: List[str]):
        self.keywords = keywords
        self.level0_combinations = generate_keyword_combinations(keywords)
        self.level1_keywords = keywords
        self.level2_synonyms: Dict[str, List[str]] = {}
        self.level3_pairs = generate_keyword_magical_pairs(keywords)
        self._synonym_terms: Optional[List[str]] = None  # cached flattened synonyms

    # ---------- Low-level search helpers ----------
    def _exact_phrase_search(
        self,
        phrase: str,
        limit: int = 50,
        exclude_texts: Set[str] = None,
        slop: int = 0,
    ) -> List[Dict[str, Any]]:
        must_not = []
        if exclude_texts:
            for text in list(exclude_texts)[:50]:
                must_not.append({"match_phrase": {"text": text}})

        phrase_query = {
            "match_phrase": {
                "text": {
                    "query": phrase,
                    "slop": slop,
                }
            }
        }

        if must_not:
            query = {"bool": {"must": [phrase_query], "must_not": must_not}}
        else:
            query = phrase_query

        body = {"size": limit, "query": query}

        try:
            resp = es.search(index=INDEX, body=body)
            results: List[Dict[str, Any]] = []
            seen_texts = set()
            for hit in resp["hits"]["hits"]:
                src = hit["_source"]
                text = src["text"]
                if text in seen_texts:
                    continue
                if exclude_texts and text in exclude_texts:
                    continue
                seen_texts.add(text)
                results.append(
                    {
                        "text": text,
                        "level": src.get("level", 0),
                        "score": hit.get("_score", 1.0),
                        "sentence_index": src.get("sentence_index", 0),
                        "_id": hit["_id"],
                    }
                )
            return results
        except Exception as e:
            logger.error(f"Phrase search error for '{phrase}': {e}")
            return []

    def _text_search(
        self,
        query_text: str,
        limit: int = 15,
        exclude_texts: Set[str] = None,
        use_vector: bool = True,
        match_type: str = "match",
        require_all_words: bool = False,
    ) -> List[Dict[str, Any]]:
        must_not = []
        if exclude_texts:
            for text in list(exclude_texts)[:50]:
                must_not.append({"match_phrase": {"text": text}})

        if match_type == "match_phrase":
            text_query = {"match_phrase": {"text": {"query": query_text, "slop": 0}}}
        elif match_type == "match_phrase_flex":
            text_query = {"match_phrase": {"text": {"query": query_text, "slop": 2}}}
        elif match_type == "multi_match":
            text_query = {
                "multi_match": {
                    "query": query_text,
                    "fields": ["text"],
                    "type": "best_fields",
                    "operator": "and" if require_all_words else "or",
                }
            }
        else:
            text_query = {"match": {"text": {"query": query_text, "operator": "and"}}}

        bool_query = {"bool": {"must": [text_query], "must_not": must_not}} if must_not else text_query

        if use_vector:
            query_vec = get_embedding(query_text)
            body = {
                "size": limit * 3,
                "query": {
                    "script_score": {
                        "query": bool_query,
                        "script": {
                            "source": "cosineSimilarity(params.query_vector, 'embedding') + 1.0",
                            "params": {"query_vector": query_vec},
                        },
                    }
                },
            }
        else:
            body = {"size": limit * 3, "query": bool_query}

        try:
            resp = es.search(index=INDEX, body=body)
            results: List[Dict[str, Any]] = []
            seen_texts: Set[str] = set()
            for hit in resp["hits"]["hits"]:
                src = hit["_source"]
                text = src["text"]
                if text in seen_texts:
                    continue
                if exclude_texts and text in exclude_texts:
                    continue
                if require_all_words:
                    query_words = query_text.lower().split()
                    text_lower = text.lower()
                    if not all(word in text_lower for word in query_words):
                        continue
                seen_texts.add(text)
                results.append(
                    {
                        "text": text,
                        "level": src.get("level", 0),
                        "score": hit.get("_score", 1.0),
                        "sentence_index": src.get("sentence_index", 0),
                        "_id": hit["_id"],
                    }
                )
                if len(results) >= limit:
                    break
            logger.info(f"[ES Results] Found {len(results)} for '{query_text[:50]}...'")
            return results
        except Exception as e:
            logger.error(f"Search error for '{query_text[:50]}...': {e}")
            return []

    # ---------- Level fetchers ----------
    def _get_all_synonym_terms(self) -> List[str]:
        if self._synonym_terms is None:
            terms: List[str] = []
            for kw in self.keywords:
                if kw not in self.level2_synonyms:
                    self.level2_synonyms[kw] = generate_synonyms(kw)
                terms.extend(self.level2_synonyms[kw])
            seen = set()
            deduped = []
            for t in terms:
                if t not in seen:
                    seen.add(t)
                    deduped.append(t)
            self._synonym_terms = deduped
        return self._synonym_terms

    def fetch_level0_sentences(self, offset: int, limit: int, used_texts: Set[str]) -> Tuple[List[Dict[str, Any]], int, bool]:
        logger.info(f"[Level 0] offset={offset} limit={limit} used={len(used_texts)}")
        sentences: List[Dict[str, Any]] = []
        current_offset = offset
        while len(sentences) < limit and current_offset < len(self.level0_combinations):
            combo = self.level0_combinations[current_offset]
            query_text = " ".join(combo)
            results = self._text_search(
                query_text=query_text,
                limit=limit - len(sentences),
                exclude_texts=used_texts,
                use_vector=True,
                match_type="multi_match",
                require_all_words=True,
            )
            for r in results:
                if r["text"] not in used_texts:
                    sentences.append(r)
                    used_texts.add(r["text"])
                if len(sentences) >= limit:
                    break
            current_offset += 1
        if len(sentences) < limit:
            query_text = " ".join(self.keywords)
            results = self._text_search(
                query_text=query_text,
                limit=(limit - len(sentences)) * 2,
                exclude_texts=used_texts,
                use_vector=True,
                match_type="match",
            )
            for r in results:
                if r["text"] not in used_texts:
                    sentences.append(r)
                    used_texts.add(r["text"])
                if len(sentences) >= limit:
                    break
        exhausted = current_offset >= len(self.level0_combinations) and len(sentences) < limit // 2
        return sentences, current_offset, exhausted

    def fetch_level1_keyword_magic(
        self,
        offset: int,
        limit: int,
        used_texts: Set[str],
        sentences_per_pair: int = 3,
        single_keyword_mode: bool = False,
    ) -> Tuple[List[Dict[str, Any]], int, bool, Optional[str]]:
        sentences: List[Dict[str, Any]] = []
        current_offset = offset
        magic_words = get_magical_words_for_level3()
        current_magic_word = None

        if single_keyword_mode and len(self.keywords) == 1:
            keyword = self.keywords[0]
            while len(sentences) < limit and current_offset < len(magic_words):
                magic = magic_words[current_offset]
                current_magic_word = magic
                phrase = f"{keyword} {magic}"
                exact_results = self._exact_phrase_search(
                    phrase=phrase,
                    limit=100,
                    exclude_texts=used_texts,
                    slop=0,
                )
                for r in exact_results:
                    if r["text"] not in used_texts:
                        r["magic_word"] = magic
                        r["sub_level"] = f"1.{current_offset}"
                        r["match_type"] = "exact_phrase"
                        sentences.append(r)
                        used_texts.add(r["text"])
                    if len(sentences) >= limit:
                        break
                current_offset += 1
                if len(sentences) >= limit:
                    break
        else:
            num_keywords = len(self.keywords) if self.keywords else 1
            magic_index = current_offset // num_keywords
            keyword_index = current_offset % num_keywords
            while len(sentences) < limit and magic_index < len(magic_words):
                magic = magic_words[magic_index]
                current_magic_word = magic
                while len(sentences) < limit and keyword_index < len(self.keywords):
                    keyword = self.keywords[keyword_index]
                    phrase = f"{keyword} {magic}"
                    results = self._text_search(
                        query_text=phrase,
                        limit=sentences_per_pair,
                        exclude_texts=used_texts,
                        use_vector=False,
                        match_type="match_phrase",
                    )
                    if len(results) < sentences_per_pair:
                        more_results = self._text_search(
                            query_text=phrase,
                            limit=sentences_per_pair - len(results),
                            exclude_texts=used_texts | {r["text"] for r in results},
                            use_vector=True,
                            match_type="match",
                        )
                        results.extend(more_results)
                    for r in results:
                        if r["text"] not in used_texts:
                            r["magic_word"] = magic
                            r["keyword_used"] = keyword
                            sentences.append(r)
                            used_texts.add(r["text"])
                        if len(sentences) >= limit:
                            break
                    keyword_index += 1
                    current_offset += 1
                if keyword_index >= len(self.keywords):
                    magic_index += 1
                    keyword_index = 0
                if len(sentences) >= limit:
                    break
        exhausted = current_offset >= len(self.level3_pairs) or (
            single_keyword_mode and current_offset >= len(magic_words)
        )
        return sentences, current_offset, exhausted, current_magic_word

    def fetch_level2_synonym_combinations(
        self, offset: int, limit: int, used_texts: Set[str]
    ) -> Tuple[List[Dict[str, Any]], int, bool]:
        sentences: List[Dict[str, Any]] = []
        current_offset = offset
        synonym_terms = self._get_all_synonym_terms()
        if not synonym_terms:
            return [], current_offset, True
        combos = generate_keyword_combinations(synonym_terms)
        while len(sentences) < limit and current_offset < len(combos):
            combo = combos[current_offset]
            query_text = " ".join(combo)
            results = self._text_search(
                query_text=query_text,
                limit=limit - len(sentences),
                exclude_texts=used_texts,
                use_vector=True,
                match_type="multi_match",
                require_all_words=True,
            )
            for r in results:
                if r["text"] not in used_texts:
                    r["synonym_combo"] = combo
                    sentences.append(r)
                    used_texts.add(r["text"])
                if len(sentences) >= limit:
                    break
            current_offset += 1
        exhausted = current_offset >= len(combos)
        return sentences, current_offset, exhausted

    def fetch_level3_synonyms_with_magic(
        self, offset: int, limit: int, used_texts: Set[str]
    ) -> Tuple[List[Dict[str, Any]], int, bool]:
        sentences: List[Dict[str, Any]] = []
        current_offset = offset
        magic_words = get_magical_words_for_level3()
        synonym_terms = self._get_all_synonym_terms()
        if not synonym_terms:
            return [], current_offset, True
        all_pairs = [(syn, magic) for syn in synonym_terms for magic in magic_words]
        while len(sentences) < limit and current_offset < len(all_pairs):
            synonym, magic = all_pairs[current_offset]
            phrase = f"{synonym} {magic}"
            exact_results = self._exact_phrase_search(
                phrase=phrase,
                limit=50,
                exclude_texts=used_texts,
                slop=0,
            )
            for r in exact_results:
                if r["text"] not in used_texts:
                    r["synonym_used"] = synonym
                    r["magic_word"] = magic
                    r["match_type"] = "exact_phrase"
                    sentences.append(r)
                    used_texts.add(r["text"])
                if len(sentences) >= limit:
                    break
            current_offset += 1
            if len(sentences) >= limit:
                break
        exhausted = current_offset >= len(all_pairs)
        return sentences, current_offset, exhausted

    def fetch_level1_sentences(
        self,
        offset: int,
        limit: int,
        used_texts: Set[str],
        sentences_per_keyword: int = 50,
    ) -> Tuple[List[Dict[str, Any]], int, bool]:
        """Fallback keyword-only search (not used in main 0-4 flow)."""
        sentences: List[Dict[str, Any]] = []
        current_offset = offset
        while len(sentences) < limit and current_offset < len(self.level1_keywords):
            keyword = self.level1_keywords[current_offset]
            results = self._text_search(
                query_text=keyword,
                limit=sentences_per_keyword,
                exclude_texts=used_texts,
                use_vector=True,
                match_type="match",
                require_all_words=True,
            )
            for r in results:
                if r["text"] not in used_texts:
                    r["keyword_matched"] = keyword
                    sentences.append(r)
                    used_texts.add(r["text"])
                if len(sentences) >= limit:
                    break
            current_offset += 1
        exhausted = current_offset >= len(self.level1_keywords)
        return sentences, current_offset, exhausted


def get_next_batch(
    session_state: Dict[str, Any],
    keywords: List[str],
    batch_size: int = 15,
    enabled_levels: Optional[List[int]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any], int]:
    retriever = MultiLevelRetriever(keywords)
    is_single_keyword = len(keywords) == 1
    if enabled_levels is None:
        enabled_levels = [0, 1, 2, 3, 4]

    logger.info(f"[get_next_batch] Searching levels: {enabled_levels}")

    sentences: List[Dict[str, Any]] = []
    current_level = session_state.get("current_level", 0)
    level_offsets = session_state.get(
        "level_offsets", {"0": 0, "1": 0, "2": 0, "3": 0, "4": 0}
    )
    used_texts = set(session_state.get("used_sentence_ids", []))
    level_used = current_level

    while len(sentences) < batch_size and current_level <= 4:
        if current_level not in enabled_levels:
            current_level += 1
            continue

        remaining = batch_size - len(sentences)

        if current_level == 0:
            if is_single_keyword:
                current_level = 1
                continue
            new_sents, new_offset, exhausted = retriever.fetch_level0_sentences(
                offset=level_offsets.get("0", 0),
                limit=remaining,
                used_texts=used_texts,
            )
            level_offsets["0"] = new_offset

        elif current_level == 1:
            new_sents, new_offset, exhausted, magic_word = retriever.fetch_level1_keyword_magic(
                offset=level_offsets.get("1", 0),
                limit=remaining,
                used_texts=used_texts,
                single_keyword_mode=is_single_keyword,
            )
            level_offsets["1"] = new_offset
            if magic_word:
                level_offsets["1_magic_word"] = magic_word

        elif current_level == 2:
            new_sents, new_offset, exhausted = retriever.fetch_level2_synonym_combinations(
                offset=level_offsets.get("2", 0),
                limit=remaining,
                used_texts=used_texts,
            )
            level_offsets["2"] = new_offset

        elif current_level == 3:
            new_sents, new_offset, exhausted = retriever.fetch_level3_synonyms_with_magic(
                offset=level_offsets.get("3", 0),
                limit=remaining,
                used_texts=used_texts,
            )
            level_offsets["3"] = new_offset

        elif current_level == 4:
            query_text = " ".join(keywords)
            new_sents = retriever._text_search(
                query_text=query_text,
                limit=remaining,
                exclude_texts=used_texts,
                use_vector=True,
                match_type="match",
                require_all_words=False,
            )
            exhausted = True
        else:
            break

        for sent in new_sents:
            sent["level"] = current_level
        sentences.extend(new_sents)
        for s in new_sents:
            used_texts.add(s["text"])

        if exhausted or not new_sents:
            current_level += 1
            level_used = current_level - 1
        else:
            level_used = current_level

    updated_state = {
        "current_level": current_level,
        "level_offsets": level_offsets,
        "used_sentence_ids": list(used_texts),
    }

    return sentences, updated_state, level_used
