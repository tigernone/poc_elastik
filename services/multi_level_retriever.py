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
from services.deduplicator import (
    is_duplicate,
    normalize_text,
    get_text_fingerprint,
    deduplicate_sentences
)

logger = logging.getLogger(__name__)
INDEX = settings.ES_INDEX_NAME

# Minimum sentence length to filter out short/meaningless sentences
MIN_SENTENCE_LENGTH = 20  # At least 20 characters


def is_valid_sentence(text: str) -> bool:
    """Check if sentence is valid (not too short, not just keywords)."""
    if not text or len(text.strip()) < MIN_SENTENCE_LENGTH:
        return False
    # Count words - need at least 4 words for a meaningful sentence
    words = text.strip().split()
    if len(words) < 4:
        return False
    return True


def get_pure_semantic_search(
    query: str,
    limit: int = 5,
    exclude_texts: Set[str] = None
) -> List[Dict[str, Any]]:
    """
    Pure semantic/vector search - NO keyword filtering.
    Always returns top K nearest neighbors based on cosine similarity.
    
    Use this as a fallback to ALWAYS get relevant results even when
    keyword-based searches fail.
    
    Args:
        query: Original user query (full sentence)
        limit: Number of results to return
        exclude_texts: Texts to exclude from results
        
    Returns:
        List of {text, level, score, sentence_index, _id}
    """
    logger.info(f"[Pure Semantic Search] query='{query[:50]}...', limit={limit}")
    
    # Get embedding for the full query
    query_vec = get_embedding(query)
    
    # Build must_not clause for exclusions
    must_not = []
    if exclude_texts:
        for text in list(exclude_texts)[:100]:  # Limit to avoid query too large
            must_not.append({"match_phrase": {"text": text}})
    
    # Pure vector search - NO text filtering, just cosine similarity
    body = {
        "size": limit * 5,  # Get more to account for filtering short sentences
        "query": {
            "script_score": {
                "query": {
                    "bool": {
                        "must": [{"match_all": {}}],  # No keyword filter
                        "must_not": must_not
                    }
                } if must_not else {"match_all": {}},
                "script": {
                    "source": "cosineSimilarity(params.query_vector, 'embedding') + 1.0",
                    "params": {"query_vector": query_vec},
                },
            }
        },
    }
    
    try:
        resp = es.search(index=INDEX, body=body)
        results: List[Dict[str, Any]] = []
        seen_texts: Set[str] = set()
        
        for hit in resp["hits"]["hits"]:
            src = hit["_source"]
            text = src["text"]
            
            # Skip short/invalid sentences
            if not is_valid_sentence(text):
                continue
            
            # Check for exact or near-duplicate (95% similarity)
            if is_duplicate(text, seen_texts, similarity_threshold=0.95):
                continue
            if exclude_texts and is_duplicate(text, exclude_texts, similarity_threshold=0.95):
                continue
                
            seen_texts.add(text)
            results.append({
                "text": text,
                "level": 0,  # Use 0 for semantic search (source_type will show "Vector/Semantic Search")
                "score": hit.get("_score", 1.0),
                "sentence_index": src.get("sentence_index", 0),
                "_id": hit["_id"],
                "source": "pure_semantic"  # Mark as semantic search result
            })
            
            if len(results) >= limit:
                break
        
        logger.info(f"[Pure Semantic Search] Found {len(results)} semantically similar sentences")
        return results
        
    except Exception as e:
        logger.error(f"[Pure Semantic Search] Error: {e}")
        return []


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

        body = {"size": limit * 3, "query": query}  # Get more to filter

        try:
            resp = es.search(index=INDEX, body=body)
            results: List[Dict[str, Any]] = []
            seen_texts = set()
            for hit in resp["hits"]["hits"]:
                src = hit["_source"]
                text = src["text"]
                # Skip short/invalid sentences
                if not is_valid_sentence(text):
                    continue
                # Check for exact or near-duplicate (95% similarity)
                if is_duplicate(text, seen_texts, similarity_threshold=0.95):
                    continue
                if exclude_texts and is_duplicate(text, exclude_texts, similarity_threshold=0.95):
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
                # Skip short/invalid sentences
                if not is_valid_sentence(text):
                    continue
                # Check for exact or near-duplicate (95% similarity)
                if is_duplicate(text, seen_texts, similarity_threshold=0.95):
                    continue
                if exclude_texts and is_duplicate(text, exclude_texts, similarity_threshold=0.95):
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

    def fetch_level0_sentences(self, offset: int, limit: int, used_texts: Set[str]) -> Tuple[List[Dict[str, Any]], int, bool, Set[str]]:
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
                # Use is_duplicate to catch near-duplicates (waked vs wakened)
                if not is_duplicate(r["text"], used_texts, similarity_threshold=0.95):
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
                # Use is_duplicate to catch near-duplicates (waked vs wakened)
                if not is_duplicate(r["text"], used_texts, similarity_threshold=0.95):
                    sentences.append(r)
                    used_texts.add(r["text"])
                if len(sentences) >= limit:
                    break
        exhausted = current_offset >= len(self.level0_combinations) and len(sentences) < limit // 2
        
        # CRITICAL: Batch deduplicate at end (faster than checking each item)
        sentences, used_texts = deduplicate_sentences(sentences, existing_texts=used_texts, similarity_threshold=0.95)
        
        return sentences, current_offset, exhausted, used_texts

    def fetch_level1_keyword_magic(
        self,
        offset: int,
        limit: int,
        used_texts: Set[str],
        sentences_per_pair: int = 3,
        single_keyword_mode: bool = False,
    ) -> Tuple[List[Dict[str, Any]], int, bool, Optional[str], Set[str]]:
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
                    # Use is_duplicate to catch near-duplicates (waked vs wakened)
                    if not is_duplicate(r["text"], used_texts, similarity_threshold=0.95):
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
                        # Use is_duplicate to catch near-duplicates (waked vs wakened)
                        if not is_duplicate(r["text"], used_texts, similarity_threshold=0.95):
                            r["magic_word"] = magic
                            r["keyword_used"] = keyword
                            sentences.append(r)
                            used_texts.add(r["text"])
                        else:
                            logger.debug(f"[Level 1] Skipped duplicate: '{r['text'][:60]}...'")
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
        
        # CRITICAL: Batch deduplicate at end (faster than checking each item)
        # Log before and after for debugging
        logger.info(f"[Level 1] Before batch dedup: {len(sentences)} sentences, used_texts has {len(used_texts)} items")
        for sent in sentences[:2]:
            logger.info(f"[Level 1] Sentence before dedup: '{sent.get('text', '')[:80]}...'")
        sentences, used_texts = deduplicate_sentences(sentences, existing_texts=used_texts, similarity_threshold=0.95)
        logger.info(f"[Level 1] After batch dedup: {len(sentences)} sentences")
        for sent in sentences[:2]:
            logger.info(f"[Level 1] Sentence after dedup: '{sent.get('text', '')[:80]}...'")
        
        return sentences, current_offset, exhausted, current_magic_word, used_texts

    def fetch_level2_synonym_combinations(
        self, offset: int, limit: int, used_texts: Set[str]
    ) -> Tuple[List[Dict[str, Any]], int, bool, Set[str]]:
        sentences: List[Dict[str, Any]] = []
        current_offset = offset
        synonym_terms = self._get_all_synonym_terms()
        if not synonym_terms:
            return [], current_offset, True
        
        # OPTIMIZATION: Limit combinations to avoid exponential explosion
        # Use only top synonyms and smaller combo sizes
        max_terms = min(len(synonym_terms), 6)  # Max 6 terms instead of all
        synonym_terms = synonym_terms[:max_terms]
        
        combos = generate_keyword_combinations(synonym_terms)
        
        # OPTIMIZATION: Limit max combinations to search
        max_combos = min(len(combos), 50)  # Only search first 50 combos
        combos = combos[:max_combos]
        
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
                # Use is_duplicate to catch near-duplicates (waked vs wakened)
                if not is_duplicate(r["text"], used_texts, similarity_threshold=0.95):
                    r["synonym_combo"] = combo
                    sentences.append(r)
                    used_texts.add(r["text"])
                if len(sentences) >= limit:
                    break
            current_offset += 1
        exhausted = current_offset >= len(combos)
        
        # CRITICAL: Batch deduplicate at end (faster than checking each item)
        sentences, used_texts = deduplicate_sentences(sentences, existing_texts=used_texts, similarity_threshold=0.95)
        
        return sentences, current_offset, exhausted, used_texts

    def fetch_level3_synonyms_with_magic(
        self, offset: int, limit: int, used_texts: Set[str]
    ) -> Tuple[List[Dict[str, Any]], int, bool, Set[str]]:
        sentences: List[Dict[str, Any]] = []
        current_offset = offset
        magic_words = get_magical_words_for_level3()
        synonym_terms = self._get_all_synonym_terms()
        if not synonym_terms:
            return [], current_offset, True
        
        # OPTIMIZATION: Limit synonym terms and magic words
        max_synonyms = min(len(synonym_terms), 5)  # Max 5 synonym terms
        max_magic = min(len(magic_words), 20)      # Max 20 magic words
        synonym_terms = synonym_terms[:max_synonyms]
        magic_words = magic_words[:max_magic]
        
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
                # Use is_duplicate to catch near-duplicates (waked vs wakened)
                if not is_duplicate(r["text"], used_texts, similarity_threshold=0.95):
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
        exhausted = current_offset >= len(self.level3_pairs)
        
        # CRITICAL: Batch deduplicate at end (faster than checking each item)
        sentences, used_texts = deduplicate_sentences(sentences, existing_texts=used_texts, similarity_threshold=0.95)
        
        return sentences, current_offset, exhausted, used_texts

    def fetch_level1_sentences(
        self,
        offset: int,
        limit: int,
        used_texts: Set[str],
        sentences_per_keyword: int = 50,
    ) -> Tuple[List[Dict[str, Any]], int, bool, Set[str]]:
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
                # Use is_duplicate to catch near-duplicates (waked vs wakened)
                if not is_duplicate(r["text"], used_texts, similarity_threshold=0.95):
                    r["keyword_matched"] = keyword
                    sentences.append(r)
                    used_texts.add(r["text"])
                if len(sentences) >= limit:
                    break
            current_offset += 1
        exhausted = current_offset >= len(self.level1_synonyms)
        
        # CRITICAL: Batch deduplicate at end (faster than checking each item)
        sentences, used_texts = deduplicate_sentences(sentences, existing_texts=used_texts, similarity_threshold=0.95)
        
        return sentences, current_offset, exhausted, used_texts


def get_next_batch(
    session_state: Dict[str, Any],
    keywords: List[str],
    batch_size: int = 15,
    enabled_levels: Optional[List[int]] = None,
    original_query: str = None,  # NEW: Original query for semantic search
    semantic_count: int = 5,  # NEW: Always get 5 semantic results
) -> Tuple[List[Dict[str, Any]], Dict[str, Any], int]:
    """
    Get next batch of sentences using multi-level retrieval.
    
    NEW BEHAVIOR:
    - Get (batch_size - semantic_count) from keyword-based levels (e.g., 10 sentences)
    - ALWAYS get semantic_count from pure semantic search (e.g., 5 sentences)
    - This ensures we ALWAYS have relevant results even if keyword search fails
    
    Args:
        session_state: Current session state
        keywords: Extracted keywords
        batch_size: Total sentences to return (default 15)
        enabled_levels: Which levels to search (default all)
        original_query: Original user query for semantic search
        semantic_count: How many pure semantic results to include (default 5)
    """
    retriever = MultiLevelRetriever(keywords)
    is_single_keyword = len(keywords) == 1
    if enabled_levels is None:
        enabled_levels = [0, 1, 2, 3, 4]

    logger.info(f"[get_next_batch] Strategy: {batch_size - semantic_count} keyword-based + {semantic_count} semantic")
    logger.info(f"[get_next_batch] Searching levels: {enabled_levels}")

    # Calculate how many to get from keyword-based levels
    keyword_batch_size = max(1, batch_size - semantic_count)
    
    sentences: List[Dict[str, Any]] = []
    current_level = session_state.get("current_level", 0)
    level_offsets = session_state.get(
        "level_offsets", {"0": 0, "1": 0, "2": 0, "3": 0, "4": 0}
    )
    used_texts = set(session_state.get("used_sentence_ids", []))
    level_used = current_level

    # PART 1: Get keyword-based sentences (10 sentences)
    while len(sentences) < keyword_batch_size and current_level <= 4:
        if current_level not in enabled_levels:
            current_level += 1
            continue

        remaining = keyword_batch_size - len(sentences)

        if current_level == 0:
            if is_single_keyword:
                current_level = 1
                continue
            new_sents, new_offset, exhausted, used_texts = retriever.fetch_level0_sentences(
                offset=level_offsets.get("0", 0),
                limit=remaining,
                used_texts=used_texts,
            )
            level_offsets["0"] = new_offset

        elif current_level == 1:
            new_sents, new_offset, exhausted, magic_word, used_texts = retriever.fetch_level1_keyword_magic(
                offset=level_offsets.get("1", 0),
                limit=remaining,
                used_texts=used_texts,
                single_keyword_mode=is_single_keyword,
            )
            level_offsets["1"] = new_offset
            if magic_word:
                level_offsets["1_magic_word"] = magic_word

        elif current_level == 2:
            new_sents, new_offset, exhausted, used_texts = retriever.fetch_level2_synonym_combinations(
                offset=level_offsets.get("2", 0),
                limit=remaining,
                used_texts=used_texts,
            )
            level_offsets["2"] = new_offset

        elif current_level == 3:
            new_sents, new_offset, exhausted, used_texts = retriever.fetch_level3_synonyms_with_magic(
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
            sent["source"] = f"level_{current_level}"  # Mark source
        sentences.extend(new_sents)
        for s in new_sents:
            used_texts.add(s["text"])

        if exhausted or not new_sents:
            current_level += 1
            level_used = current_level - 1
        else:
            level_used = current_level

    # PART 2: ALWAYS get semantic results (5 sentences)
    semantic_results = []
    if original_query:
        logger.info(f"[get_next_batch] Adding {semantic_count} pure semantic results")
        semantic_results = get_pure_semantic_search(
            query=original_query,
            limit=semantic_count,
            exclude_texts=used_texts
        )
        
        # Mark as semantic with clear labels
        for sent in semantic_results:
            sent["source"] = "vector_search"  # Changed to "vector_search"
            sent["source_type"] = "Vector"  # Human-readable label (short)
            sent["is_primary_source"] = True  # Mark as primary
        
        # Add to used_texts to avoid duplicates in future calls
        for s in semantic_results:
            used_texts.add(s["text"])
        
        logger.info(f"[get_next_batch] Total: {len(sentences) + len(semantic_results)} sentences ({len(sentences)} keyword + {len(semantic_results)} semantic)")
    else:
        logger.warning("[get_next_batch] No original_query provided, skipping semantic search")

    # Mark keyword results with clear labels
    for sent in sentences:
        sent["source_type"] = f"Level {sent.get('level', 0)}"
        sent["is_primary_source"] = False  # Mark as secondary

    # IMPORTANT: Put semantic results FIRST (on top), keyword results after
    final_results = semantic_results + sentences

    # CRITICAL: Apply fuzzy deduplication WITHIN final_results only (95% similarity)
    # This catches near-duplicates between semantic and keyword results
    # NOTE: Do NOT pass existing_texts=used_texts here - we want to keep all results
    #       that are different from each other, even if they were used in intermediate steps
    initial_seen = set()  # Start fresh for final dedup
    deduplicated_final, final_seen_texts = deduplicate_sentences(final_results, existing_texts=initial_seen, similarity_threshold=0.95)
    removed_count = len(final_results) - len(deduplicated_final)
    
    logger.info(f"[get_next_batch] FINAL DEDUP INPUT: {len(final_results)} sentences")
    for i, sent in enumerate(final_results[:3]):
        logger.debug(f"[get_next_batch]   #{i}: '{sent.get('text', '')[:80]}...'")
    
    if removed_count > 0:
        logger.info(f"[Dedup] Final results: {len(final_results)} -> {len(deduplicated_final)} (removed {removed_count} near-duplicates)")
    else:
        logger.info(f"[Dedup] Final results: {len(final_results)} (no near-duplicates found)")
    
    # Update used_texts with all texts from final results (for future calls)
    for sent in deduplicated_final:
        used_texts.add(sent.get("text", ""))
    
    updated_state = {
        "current_level": current_level,
        "level_offsets": level_offsets,
        "used_sentence_ids": list(used_texts),
    }

    return deduplicated_final, updated_state, level_used
