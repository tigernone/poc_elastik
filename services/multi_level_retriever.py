# services/multi_level_retriever.py
"""
Multi-Level Retriever - 4 Level Search System
==============================================

FOR SINGLE KEYWORD (e.g., "Where is heaven?"):
-----------------------------------------------
Level 1: Keyword + Magic Words
    - Search: "heaven is", "heaven was", "heaven means"
    - Finds sentences with BOTH keyword AND magic word
    - Example: 13 sentences with "heaven" + "is"

Level 2: Synonyms + Magic Words  
    - Search: "paradise is", "celestial was", "sky means"
    - Finds sentences with synonym AND magic word
    - Example: sentences with "paradise" + "is"

Level 3: Only Keyword (fallback)
    - Search: "heaven" alone
    - Finds remaining sentences containing keyword
    - Example: all other sentences with "heaven"

FOR MULTIPLE KEYWORDS (e.g., "What is grace and freedom?"):
-----------------------------------------------------------
Level 0: Keyword Combinations
    - Search: "grace AND freedom" together

Level 1: Keyword + Magic Words
    - Search: "grace is", "freedom was"

Level 2: Synonyms only
    - Search: "mercy", "liberty"

Level 3: Single Keywords (fallback)
    - Search: "grace", "freedom" individually
"""
from typing import List, Dict, Any, Set, Tuple, Optional
from services.embedder import get_embedding
from vector.elastic_client import es
from config import settings
from services.keyword_extractor import (
    generate_keyword_combinations,
    generate_synonyms,
    generate_keyword_magical_pairs
)

INDEX = settings.ES_INDEX_NAME


class MultiLevelRetriever:
    """
    Multi-level sentence retrieval for progressive exploration.
    """
    
    def __init__(self, keywords: List[str]):
        """
        Initialize with extracted keywords.
        
        Args:
            keywords: Clean keywords (already filtered from magic words)
        """
        self.keywords = keywords
        
        # Pre-generate combinations for each level
        self.level0_combinations = generate_keyword_combinations(keywords)
        self.level1_keywords = keywords  # Single keywords
        self.level2_synonyms = {}  # Will be populated on demand
        self.level3_pairs = generate_keyword_magical_pairs(keywords)
        
        # Track which items have been fully explored
        self.level0_index = 0
        self.level1_index = 0
        self.level2_keyword_index = 0
        self.level2_synonym_index = 0
        self.level3_index = 0
    
    def _exact_phrase_search(
        self,
        phrase: str,
        limit: int = 50,
        exclude_texts: Set[str] = None,
        slop: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Search for exact phrase matches with configurable slop.
        
        Args:
            phrase: Phrase to search (e.g., "heaven is")
            limit: Max results
            exclude_texts: Sentences to exclude
            slop: Number of words allowed between phrase words
                  0 = exact consecutive match ("heaven is")
                  1 = 1 word gap allowed ("heaven [x] is")
                  2 = 2 words gap allowed
        """
        must_not = []
        if exclude_texts:
            for text in list(exclude_texts)[:50]:
                must_not.append({"match_phrase": {"text": text}})
        
        # Build match_phrase query with slop
        phrase_query = {
            "match_phrase": {
                "text": {
                    "query": phrase,
                    "slop": slop
                }
            }
        }
        
        if must_not:
            query = {
                "bool": {
                    "must": [phrase_query],
                    "must_not": must_not
                }
            }
        else:
            query = phrase_query
        
        body = {
            "size": limit,
            "query": query
        }
        
        try:
            resp = es.search(index=INDEX, body=body)
            results = []
            seen_texts = set()
            
            for hit in resp["hits"]["hits"]:
                src = hit["_source"]
                text = src["text"]
                
                if text in seen_texts:
                    continue
                if exclude_texts and text in exclude_texts:
                    continue
                
                seen_texts.add(text)
                results.append({
                    "text": text,
                    "level": src.get("level", 0),
                    "score": hit["_score"],
                    "sentence_index": src.get("sentence_index", 0),
                    "_id": hit["_id"]
                })
            
            return results
        except Exception as e:
            print(f"Phrase search error: {e}")
            return []
    
    def _text_search(
        self,
        query_text: str,
        limit: int = 15,
        exclude_texts: Set[str] = None,
        use_vector: bool = True,
        match_type: str = "match"
    ) -> List[Dict[str, Any]]:
        """
        Search Elasticsearch with text and optional vector scoring.
        
        Args:
            query_text: Text to search
            limit: Max results
            exclude_texts: Sentences to exclude
            use_vector: Whether to combine with vector search
            match_type: "match", "match_phrase", or "multi_match"
        """
        must_not = []
        if exclude_texts:
            for text in list(exclude_texts)[:50]:  # Limit to avoid huge query
                must_not.append({"match_phrase": {"text": text}})
        
        # Build text query based on type
        if match_type == "match_phrase":
            # Use slop=0 for exact consecutive match, slop=1 allows 1 word gap
            text_query = {
                "match_phrase": {
                    "text": {
                        "query": query_text,
                        "slop": 0  # Exact consecutive words
                    }
                }
            }
        elif match_type == "match_phrase_flex":
            # Allow up to 2 words between keywords
            text_query = {
                "match_phrase": {
                    "text": {
                        "query": query_text,
                        "slop": 2
                    }
                }
            }
        elif match_type == "multi_match":
            text_query = {
                "multi_match": {
                    "query": query_text,
                    "fields": ["text"],
                    "type": "best_fields"
                }
            }
        else:
            text_query = {"match": {"text": {"query": query_text, "operator": "and"}}}
        
        # Combine with bool query if we have exclusions
        if must_not:
            bool_query = {
                "bool": {
                    "must": [text_query],
                    "must_not": must_not
                }
            }
        else:
            bool_query = text_query
        
        # Add vector scoring if requested
        if use_vector:
            query_vec = get_embedding(query_text)
            body = {
                "size": limit * 2,  # Get more for deduplication
                "query": {
                    "script_score": {
                        "query": bool_query,
                        "script": {
                            "source": "cosineSimilarity(params.query_vector, 'embedding') + 1.0",
                            "params": {"query_vector": query_vec}
                        }
                    }
                }
            }
        else:
            body = {
                "size": limit * 2,
                "query": bool_query
            }
        
        try:
            resp = es.search(index=INDEX, body=body)
            results = []
            seen_texts = set()
            
            for hit in resp["hits"]["hits"]:
                src = hit["_source"]
                text = src["text"]
                
                # Deduplicate
                if text in seen_texts:
                    continue
                if exclude_texts and text in exclude_texts:
                    continue
                    
                seen_texts.add(text)
                results.append({
                    "text": text,
                    "level": src.get("level", 0),
                    "score": hit["_score"],
                    "sentence_index": src.get("sentence_index", 0),
                    "_id": hit["_id"]
                })
                
                if len(results) >= limit:
                    break
            
            return results
        except Exception as e:
            print(f"Search error: {e}")
            return []
    
    def fetch_level0_sentences(
        self,
        offset: int,
        limit: int,
        used_texts: Set[str]
    ) -> Tuple[List[Dict[str, Any]], int, bool]:
        """
        Level 0: Keyword combinations search.
        Starts with most specific (all keywords) and moves to less specific.
        Also includes pure vector search on original keywords.
        
        Returns: (sentences, new_offset, exhausted)
        """
        sentences = []
        current_offset = offset
        
        # First try combinations
        while len(sentences) < limit and current_offset < len(self.level0_combinations):
            combo = self.level0_combinations[current_offset]
            query_text = " ".join(combo)
            
            # Search for this combination
            results = self._text_search(
                query_text=query_text,
                limit=limit - len(sentences),
                exclude_texts=used_texts,
                use_vector=True,
                match_type="multi_match"
            )
            
            # Add non-duplicate sentences
            for r in results:
                if r["text"] not in used_texts:
                    sentences.append(r)
                    used_texts.add(r["text"])
                if len(sentences) >= limit:
                    break
            
            current_offset += 1
        
        # If we still need more, do pure vector search
        if len(sentences) < limit:
            query_text = " ".join(self.keywords)
            results = self._text_search(
                query_text=query_text,
                limit=(limit - len(sentences)) * 2,
                exclude_texts=used_texts,
                use_vector=True,
                match_type="match"
            )
            for r in results:
                if r["text"] not in used_texts:
                    sentences.append(r)
                    used_texts.add(r["text"])
                if len(sentences) >= limit:
                    break
        
        exhausted = current_offset >= len(self.level0_combinations) and len(sentences) < limit // 2
        return sentences, current_offset, exhausted
    
    def fetch_level1_sentences(
        self,
        offset: int,
        limit: int,
        used_texts: Set[str],
        sentences_per_keyword: int = 50  # Increased from 5 to get ALL matching sentences
    ) -> Tuple[List[Dict[str, Any]], int, bool]:
        """
        Level 1: Single keyword search.
        Get ALL sentences containing each keyword (up to sentences_per_keyword).
        
        Returns: (sentences, new_offset, exhausted)
        """
        sentences = []
        current_offset = offset
        
        while len(sentences) < limit and current_offset < len(self.level1_keywords):
            keyword = self.level1_keywords[current_offset]
            
            print(f"[Level 1] Searching for keyword: '{keyword}'")
            
            # Search for single keyword - get ALL matching sentences
            results = self._text_search(
                query_text=keyword,
                limit=sentences_per_keyword,  # Get many more matches
                exclude_texts=used_texts,
                use_vector=True,
                match_type="match"
            )
            
            print(f"[Level 1] Found {len(results)} sentences containing '{keyword}'")
            
            for r in results:
                if r["text"] not in used_texts:
                    r["keyword_matched"] = keyword  # Track which keyword matched
                    sentences.append(r)
                    used_texts.add(r["text"])
                if len(sentences) >= limit:
                    break
            
            current_offset += 1
        
        exhausted = current_offset >= len(self.level1_keywords)
        return sentences, current_offset, exhausted
    
    def fetch_level2_sentences(
        self,
        keyword_offset: int,
        synonym_offset: int,
        limit: int,
        used_texts: Set[str]
    ) -> Tuple[List[Dict[str, Any]], int, int, bool]:
        """
        Level 2: Synonym-based search (original - for multiple keywords).
        Generate synonyms for each keyword and search.
        
        Returns: (sentences, new_keyword_offset, new_synonym_offset, exhausted)
        """
        sentences = []
        k_offset = keyword_offset
        s_offset = synonym_offset
        
        while len(sentences) < limit and k_offset < len(self.keywords):
            keyword = self.keywords[k_offset]
            
            # Generate synonyms if not cached
            if keyword not in self.level2_synonyms:
                self.level2_synonyms[keyword] = generate_synonyms(keyword)
            
            synonyms = self.level2_synonyms[keyword]
            
            while len(sentences) < limit and s_offset < len(synonyms):
                synonym = synonyms[s_offset]
                
                results = self._text_search(
                    query_text=synonym,
                    limit=5,  # Few sentences per synonym
                    exclude_texts=used_texts,
                    use_vector=True,
                    match_type="match"
                )
                
                for r in results:
                    if r["text"] not in used_texts:
                        sentences.append(r)
                        used_texts.add(r["text"])
                    if len(sentences) >= limit:
                        break
                
                s_offset += 1
            
            # Move to next keyword if synonyms exhausted
            if s_offset >= len(synonyms):
                k_offset += 1
                s_offset = 0
        
        exhausted = k_offset >= len(self.keywords)
        return sentences, k_offset, s_offset, exhausted

    def fetch_level2_synonyms_with_magic(
        self,
        offset: int,
        limit: int,
        used_texts: Set[str]
    ) -> Tuple[List[Dict[str, Any]], int, bool]:
        """
        Level 2 for SINGLE KEYWORD: Synonyms + Magical words.
        E.g., "paradise is", "celestial was", "sky means"
        
        Returns: (sentences, new_offset, exhausted)
        """
        from services.keyword_extractor import get_magical_words_for_level3
        
        sentences = []
        current_offset = offset
        magic_words = get_magical_words_for_level3()
        
        # Get synonyms for each keyword
        all_synonym_magic_pairs = []
        for keyword in self.keywords:
            if keyword not in self.level2_synonyms:
                self.level2_synonyms[keyword] = generate_synonyms(keyword)
            
            synonyms = self.level2_synonyms[keyword]
            # Create pairs: synonym + magic word
            for synonym in synonyms:
                for magic in magic_words:
                    all_synonym_magic_pairs.append((synonym, magic))
        
        print(f"[Level 2] Total synonym+magic pairs: {len(all_synonym_magic_pairs)}")
        
        while len(sentences) < limit and current_offset < len(all_synonym_magic_pairs):
            synonym, magic = all_synonym_magic_pairs[current_offset]
            phrase = f"{synonym} {magic}"
            
            print(f"[Level 2] Searching: '{phrase}'")
            
            # Search for synonym + magic word
            results = self._text_search(
                query_text=phrase,
                limit=5,
                exclude_texts=used_texts,
                use_vector=True,
                match_type="match"  # Finds both words in sentence
            )
            
            for r in results:
                if r["text"] not in used_texts:
                    r["synonym_used"] = synonym
                    r["magic_word"] = magic
                    sentences.append(r)
                    used_texts.add(r["text"])
                if len(sentences) >= limit:
                    break
            
            current_offset += 1
        
        exhausted = current_offset >= len(all_synonym_magic_pairs)
        return sentences, current_offset, exhausted
    
    def fetch_level3_sentences(
        self,
        offset: int,
        limit: int,
        used_texts: Set[str],
        sentences_per_pair: int = 3,
        single_keyword_mode: bool = False
    ) -> Tuple[List[Dict[str, Any]], int, bool, Optional[str]]:
        """
        Level 3: Keyword + Magical word combinations.
        E.g., "grace is", "freedom brings"
        
        NEW LOGIC:
        - Priority 1: Find ALL sentences containing exact phrase "keyword magic_word" 
        - Priority 2: After exhausting exact matches, use vector search
        
        For "heaven is" with 14 matches → should return all 14 first
        
        Returns: (sentences, new_offset, exhausted, current_magic_word)
        """
        from services.keyword_extractor import get_magical_words_for_level3
        
        sentences = []
        current_offset = offset
        magic_words = get_magical_words_for_level3()
        current_magic_word = None
        
        if single_keyword_mode and len(self.keywords) == 1:
            # SINGLE KEYWORD MODE: Sub-levels
            # Each magic word is a separate sub-level (1.0, 1.1, 1.2...)
            # IMPORTANT: Exhaust ALL results for current magic word BEFORE moving to next
            keyword = self.keywords[0]
            
            while current_offset < len(magic_words):
                magic = magic_words[current_offset]
                current_magic_word = magic
                
                # Search for BOTH orders: "keyword magic" AND "magic keyword"
                phrase1 = f"{keyword} {magic}"  # e.g., "heaven is"
                phrase2 = f"{magic} {keyword}"  # e.g., "is heaven"
                
                print(f"[Level 1.{current_offset}] Searching: '{phrase1}' or '{phrase2}'")
                
                # Priority 1: EXACT consecutive match "keyword magic" (slop=0 only!)
                # NO words allowed between keyword and magic word
                # Set HIGH limit to get ALL matching sentences
                exact_results1 = self._exact_phrase_search(
                    phrase=phrase1,
                    limit=500,  # High limit to get ALL results
                    exclude_texts=used_texts,
                    slop=0  # MUST be consecutive - no words in between
                )
                
                # Priority 2: EXACT consecutive match "magic keyword" (reversed order)
                exact_results2 = self._exact_phrase_search(
                    phrase=phrase2,
                    limit=500,  # High limit to get ALL results
                    exclude_texts=used_texts,
                    slop=0  # MUST be consecutive - no words in between
                )
                
                # Combine results (avoid duplicates)
                all_results = exact_results1
                seen_texts = {r["text"] for r in all_results}
                for r in exact_results2:
                    if r["text"] not in seen_texts:
                        all_results.append(r)
                        seen_texts.add(r["text"])
                
                print(f"[Level 1.{current_offset}] Found {len(exact_results1)} for '{phrase1}', {len(exact_results2)} for '{phrase2}' (EXACT only, no words between)")
                
                # Add ALL matches for this magic word (no limit check here)
                # This ensures we exhaust current magic word before moving to next
                for r in all_results:
                    if r["text"] not in used_texts:
                        r["magic_word"] = magic
                        r["sub_level"] = f"1.{current_offset}"
                        r["match_type"] = "exact_consecutive"
                        r["score"] = r.get("score", 1.0) * 3.0  # Boost exact matches
                        sentences.append(r)
                        used_texts.add(r["text"])
                
                # Move to next magic word ONLY after adding ALL results from current one
                current_offset += 1
                
                # Stop if we have enough sentences now
                if len(sentences) >= limit:
                    break
            
            # DON'T sort by score - preserve magic word priority order
            # The order is: all "is" results, then all "are" results, then all "was" results, etc.
        
        else:
            # MULTIPLE KEYWORDS MODE: 
            # For each magic word, get sentences for ALL keywords
            # "heaven is" → 3, "grace is" → 3, then "heaven was" → 3, "grace was" → 3...
            
            num_keywords = len(self.keywords) if self.keywords else 1
            magic_index = current_offset // num_keywords
            keyword_index = current_offset % num_keywords
            
            while len(sentences) < limit and magic_index < len(magic_words):
                magic = magic_words[magic_index]
                current_magic_word = magic
                
                while len(sentences) < limit and keyword_index < len(self.keywords):
                    keyword = self.keywords[keyword_index]
                    phrase = f"{keyword} {magic}"
                    
                    print(f"[Level 3] Searching: '{phrase}' (keyword {keyword_index + 1}/{len(self.keywords)}, magic '{magic}')")
                    
                    # Priority 1: Exact phrase match
                    results = self._text_search(
                        query_text=phrase,
                        limit=sentences_per_pair,
                        exclude_texts=used_texts,
                        use_vector=False,
                        match_type="match_phrase"
                    )
                    
                    # Priority 2: Fallback to text match with vector
                    if len(results) < sentences_per_pair:
                        more_results = self._text_search(
                            query_text=phrase,
                            limit=sentences_per_pair - len(results),
                            exclude_texts=used_texts | {r["text"] for r in results},
                            use_vector=True,
                            match_type="match"
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
                
                # Move to next magic word
                if keyword_index >= len(self.keywords):
                    magic_index += 1
                    keyword_index = 0
                
                if len(sentences) >= limit:
                    break
        
        exhausted = current_offset >= len(self.level3_pairs) or (
            single_keyword_mode and current_offset >= len(magic_words)
        )
        
        return sentences, current_offset, exhausted, current_magic_word


def get_next_batch(
    session_state: Dict[str, Any],
    keywords: List[str],
    batch_size: int = 15
) -> Tuple[List[Dict[str, Any]], Dict[str, Any], int]:
    """
    Central function to get next batch of sentences.
    
    FOR SINGLE KEYWORD (e.g., "Where is heaven?"):
        Level 1: keyword + magic words ("heaven is", "heaven was")
        Level 2: synonyms + magic words ("paradise is", "celestial was")
        Level 3: only keyword ("heaven")
    
    FOR MULTIPLE KEYWORDS:
        Level 0: keyword combinations
        Level 1: keyword + magic words
        Level 2: synonyms only
        Level 3: single keywords
    
    Args:
        session_state: Dict with current_level, level_offsets, used_sentence_ids
        keywords: Clean keywords for search
        batch_size: Number of sentences to return
    
    Returns:
        (sentences, updated_session_state, current_level_used)
    """
    retriever = MultiLevelRetriever(keywords)
    is_single_keyword = len(keywords) == 1
    
    sentences = []
    current_level = session_state.get("current_level", 0)
    level_offsets = session_state.get("level_offsets", {"0": 0, "1": 0, "2": 0, "3": 0})
    used_texts = set(session_state.get("used_sentence_ids", []))
    
    level_used = current_level
    
    while len(sentences) < batch_size and current_level <= 3:
        remaining = batch_size - len(sentences)
        
        if current_level == 0:
            # Level 0: Keyword combinations (skip for single keyword)
            if is_single_keyword:
                # Skip Level 0 for single keyword
                current_level = 1
                continue
            new_sents, new_offset, exhausted = retriever.fetch_level0_sentences(
                offset=level_offsets.get("0", 0),
                limit=remaining,
                used_texts=used_texts
            )
            level_offsets["0"] = new_offset
            
        elif current_level == 1:
            # Level 1: Keyword + Magic words (e.g., "heaven is", "heaven was")
            # For single keyword: ONLY return sentences with keyword + magic word CONSECUTIVE
            new_sents, new_offset, exhausted, magic_word = retriever.fetch_level3_sentences(
                offset=level_offsets.get("1", 0),
                limit=remaining,
                used_texts=used_texts,
                single_keyword_mode=is_single_keyword
            )
            level_offsets["1"] = new_offset
            
            # Store current magic word for display
            if magic_word:
                level_offsets["1_magic_word"] = magic_word
            
            # For single keyword: If Level 1 exhausted, DON'T go to Level 2/3
            # We only want keyword + magic word matches, no fallback to single keyword
            if is_single_keyword and exhausted:
                print(f"[INFO] Level 1 exhausted for single keyword. Found {len(sentences) + len(new_sents)} sentences with keyword+magic word.")
                sentences.extend(new_sents)
                for s in new_sents:
                    used_texts.add(s["text"])
                # STOP HERE - don't continue to Level 2/3 for single keyword
                break
            
        elif current_level == 2:
            # Level 2: For single keyword = synonyms + magic words
            #          For multiple keywords = synonyms only
            # SKIP for single keyword - we only want exact keyword + magic word
            if is_single_keyword:
                current_level = 3
                continue
            else:
                offsets = level_offsets.get("2", [0, 0])
                if isinstance(offsets, int):
                    offsets = [offsets, 0]
                new_sents, k_off, s_off, exhausted = retriever.fetch_level2_sentences(
                    keyword_offset=offsets[0],
                    synonym_offset=offsets[1],
                    limit=remaining,
                    used_texts=used_texts
                )
                level_offsets["2"] = [k_off, s_off]
            
        elif current_level == 3:
            # Level 3: Single keywords only (fallback)
            # SKIP for single keyword - we only want keyword + magic word matches
            if is_single_keyword:
                print(f"[INFO] Skipping Level 3 for single keyword. Only returning keyword+magic word matches.")
                break
            new_sents, new_offset, exhausted = retriever.fetch_level1_sentences(
                offset=level_offsets.get("3", 0),
                limit=remaining,
                used_texts=used_texts
            )
            level_offsets["3"] = new_offset
        
        else:
            break
        
        # Add level info to each sentence
        for sent in new_sents:
            sent["level"] = current_level
        
        # Add new sentences
        sentences.extend(new_sents)
        
        # Update used texts
        for s in new_sents:
            used_texts.add(s["text"])
        
        # Move to next level if current exhausted
        if exhausted or not new_sents:
            current_level += 1
            level_used = current_level - 1  # Report the level we just finished
        else:
            level_used = current_level
    
    # Update session state
    updated_state = {
        "current_level": current_level,
        "level_offsets": level_offsets,
        "used_sentence_ids": list(used_texts)
    }
    
    return sentences, updated_state, level_used
