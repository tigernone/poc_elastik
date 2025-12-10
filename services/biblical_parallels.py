"""Biblical parallels extractor and retrieval helpers."""
import json
import logging
import re
import time
from typing import Dict, List, Optional, Set, Tuple

from openai import OpenAI

from config import settings
from services.deduplicator import deduplicate_sentences, is_duplicate
from services.multi_level_retriever import MultiLevelRetriever, get_pure_semantic_search

logger = logging.getLogger(__name__)

if settings.DEEPSEEK_BASE_URL:
    client = OpenAI(api_key=settings.DEEPSEEK_API_KEY, base_url=settings.DEEPSEEK_BASE_URL)
else:
    client = OpenAI(api_key=settings.DEEPSEEK_API_KEY)

# Broad theological terms to exclude when they are not tied to a specific passage/character
GENERIC_THEOLOGY_TERMS = {
    "jesus",
    "god",
    "christ",
    "lord",
    "holy spirit",
    "grace",
    "faith",
    "love",
    "salvation",
    "redemption",
    "righteousness",
    "justification",
    "sanctification",
    "prayer",
    "repentance",
    "atonement",
    "sin",
    "forgiveness",
    "hope",
    "mercy",
    "blessing",
    "worship",
    "praise",
}


def _safe_parse_json(content: str) -> Dict[str, List[str]]:
    """Parse JSON content from LLM response robustly."""
    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    match = re.search(r"\{.*\}", content, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group())
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
    return {}


def _filter_generic(items: List[str]) -> List[str]:
    filtered: List[str] = []
    for item in items or []:
        if not isinstance(item, str):
            continue
        cleaned = item.strip()
        if not cleaned:
            continue
        lower = cleaned.lower()
        if any(term in lower for term in GENERIC_THEOLOGY_TERMS):
            continue
        filtered.append(cleaned)
    return filtered


def analyze_biblical_parallels(query: str) -> Dict[str, List[str]]:
    """Call LLM to extract concise biblical parallels before Level 0."""
    start_ts = time.time()
    prompt = f"""Analyze the following text and extract all Biblical parallels. Provide the output in four sections:

Text to analyze: "{query}"

Bible Stories / Characters – list all people, groups, or stories referenced or implied.
Scripture References – explicit or implicit verse locations (Book Chapter:Verse format).
Biblical Metaphors – symbolic language or imagery that connects to a Biblical narrative.
Keywords – list the key terms that can be used to search for related Bible passages.

Rules:
- Extract ALL relevant biblical terms, including common ones like faith, prayer, God, Lord, Jesus, etc.
- Only extract items that match the text's context.
- Output must be concise and strictly based on the given text.
- Return ONLY valid JSON with keys: stories_characters, scripture_references, biblical_metaphors, keywords.
- Each item should be 3-10 words maximum.

Output JSON format:
{{
  "stories_characters": ["Canaanite woman (woman who asked for crumbs)", "The Master's table scene"],
  "scripture_references": ["Matthew 15:21-28", "Mark 7:24-30"],
  "biblical_metaphors": ["Crumbs from the Master's table", "Children's bread"],
  "keywords": ["Canaanite woman", "Syrophoenician woman", "Crumbs", "Master's table", "faith"]
}}
"""

    logger.info(f"[BiblicalParallels] Analyzing query: {query[:100]}...")
    
    try:
        response = client.chat.completions.create(
            model=settings.CHAT_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "You extract biblical parallels as strict JSON. Include ALL relevant biblical terms found in the text, including common words like faith, prayer, God, Lord, Jesus when they appear in the query.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=500,
        )
        raw_content = response.choices[0].message.content.strip()
        logger.info(f"[BiblicalParallels] LLM raw response: {raw_content[:300]}...")
        parsed = _safe_parse_json(raw_content)
    except Exception as exc:
        logger.warning(f"[BiblicalParallels] LLM extraction failed: {exc}")
        parsed = {}

    # NOTE: Removed _filter_generic() - keep all terms LLM extracts
    # Customer wants Level 0.0 to always have data if LLM finds something
    result: Dict[str, List[str]] = {
        "stories_characters": parsed.get("stories_characters", []) or [],
        "scripture_references": parsed.get("scripture_references", []) or [],
        "biblical_metaphors": parsed.get("biblical_metaphors", []) or [],
        "keywords": parsed.get("keywords", []) or [],
    }
    
    # Clean up: ensure all items are strings and non-empty
    for key in result:
        result[key] = [str(item).strip() for item in result[key] if item and str(item).strip()]
    
    logger.info(f"[BiblicalParallels] Extracted - Stories: {result['stories_characters']}, Refs: {result['scripture_references']}, Metaphors: {result['biblical_metaphors']}, Keywords: {result['keywords']}")
    elapsed = time.time() - start_ts
    logger.info(f"[BiblicalParallels] analyze_biblical_parallels took {elapsed:.2f}s")
    return result


def _tag_sentence(sent: Dict[str, str], source_type: str, is_primary: bool = True, parallels_section: str = "") -> Dict[str, str]:
    """Tag sentence with Level 0.0 metadata for display."""
    sent["source"] = "biblical_parallels"
    # Keep numeric level for schema compatibility, add a display field for 0.0
    sent["source_type"] = f"Level 0.0 - {source_type}"
    sent["level"] = 0
    sent["level_display"] = "0.0"
    sent["is_primary_source"] = is_primary
    sent["parallels_section"] = parallels_section  # Track which section (Stories, Refs, Metaphors, Keywords)
    return sent


def gather_biblical_parallels_sentences(
    parallels: Dict[str, List[str]],
    existing_texts: Optional[Set[str]] = None,
    base_query: Optional[str] = None,
    max_iterations: int = 2,  # OPTIMIZED: Reduced from 5 to 2 - most relevant come early
    min_score_threshold: float = 1.2,  # OPTIMIZED: Higher threshold to stop earlier
    max_total_sentences: int = 50,  # OPTIMIZED: Cap total sentences to prevent overload
) -> Tuple[List[Dict[str, str]], Set[str]]:
    """
    Fetch supporting sentences for the biblical parallels layer before Level 0.
    
    OPTIMIZED LOOP LOGIC: Each category searches with limits:
    1. Max 2 iterations per category (reduced from 5)
    2. Higher score threshold to stop earlier
    3. Cap total sentences at 50
    4. Fewer items per category
    """
    collected: List[Dict[str, str]] = []
    used: Set[str] = set(existing_texts) if existing_texts else set()
    start_ts = time.time()

    # OPTIMIZED: Limit items per category to reduce API calls
    stories = parallels.get("stories_characters", [])[:3]  # Reduced from 5
    scripture_refs = parallels.get("scripture_references", [])[:2]  # Reduced from 4
    metaphors = parallels.get("biblical_metaphors", [])[:3]  # Reduced from 5
    keywords = parallels.get("keywords", [])[:5]  # Reduced from 10

    logger.info(f"[Level 0.0] Biblical Parallels - Stories: {stories}, Refs: {scripture_refs}, Metaphors: {metaphors}, Keywords: {keywords}")

    retriever = MultiLevelRetriever(keywords or ([] if base_query is None else base_query.split()))

    def loop_vector_search(items: List[str], per_iteration: int, label: str, section: str) -> int:
        """OPTIMIZED: Vector search with early exit."""
        nonlocal collected, used
        
        # Check if we've hit the total cap
        if len(collected) >= max_total_sentences:
            logger.info(f"[Level 0.0] {label}: SKIPPED (total cap {max_total_sentences} reached)")
            return 0
            
        total_collected = 0
        iteration = 0
        
        while iteration < max_iterations and len(collected) < max_total_sentences:
            iteration += 1
            iteration_count = 0
            iteration_scores = []
            
            for item in items:
                if iteration_count >= per_iteration or len(collected) >= max_total_sentences:
                    break
                remaining = min(per_iteration - iteration_count, max_total_sentences - len(collected))
                hits = get_pure_semantic_search(item, limit=remaining + 2, exclude_texts=used)
                
                for hit in hits:
                    if iteration_count >= per_iteration or len(collected) >= max_total_sentences:
                        break
                    if is_duplicate(hit["text"], used, similarity_threshold=0.95):
                        continue
                    hit["parallels_item"] = item
                    hit["iteration"] = iteration
                    iteration_scores.append(hit.get("score", 0))
                    collected.append(_tag_sentence(hit, f"{label} (iter {iteration})", is_primary=True, parallels_section=section))
                    used.add(hit["text"])
                    iteration_count += 1
                    total_collected += 1
            
            avg_score = sum(iteration_scores) / len(iteration_scores) if iteration_scores else 0
            logger.info(f"[Level 0.0] {label} iter {iteration}: {iteration_count} sentences (avg: {avg_score:.2f})")
            
            # STOP CONDITIONS
            if iteration_count == 0:
                break
            if avg_score < min_score_threshold and iteration > 1:
                break
        
        return total_collected

    def loop_keyword_vector_search(items: List[str], per_iteration: int, label: str, section: str) -> int:
        """OPTIMIZED: Keyword + vector search with early exit."""
        nonlocal collected, used
        
        if len(collected) >= max_total_sentences:
            return 0
            
        total_collected = 0
        iteration = 0
        
        while iteration < max_iterations and len(collected) < max_total_sentences:
            iteration += 1
            iteration_count = 0
            
            for item in items:
                if iteration_count >= per_iteration or len(collected) >= max_total_sentences:
                    break
                remaining = min(per_iteration - iteration_count, max_total_sentences - len(collected))
                hits = retriever._text_search(
                    query_text=item,
                    limit=remaining + 2,
                    exclude_texts=used,
                    use_vector=True,
                    match_type="match",
                    require_all_words=False,
                )
                
                for hit in hits:
                    if iteration_count >= per_iteration or len(collected) >= max_total_sentences:
                        break
                    if is_duplicate(hit["text"], used, similarity_threshold=0.95):
                        continue
                    hit["parallels_item"] = item
                    hit["iteration"] = iteration
                    collected.append(_tag_sentence(hit, f"{label} (iter {iteration})", is_primary=True, parallels_section=section))
                    used.add(hit["text"])
                    iteration_count += 1
                    total_collected += 1
            
            if iteration_count == 0:
                break
        
        return total_collected

    def loop_keyword_search(items: List[str], per_keyword: int, label: str, section: str) -> int:
        """OPTIMIZED: Keyword search with early exit."""
        nonlocal collected, used
        
        if len(collected) >= max_total_sentences:
            return 0
            
        total_collected = 0
        iteration = 0
        
        while iteration < max_iterations and len(collected) < max_total_sentences:
            iteration += 1
            iteration_count = 0
            
            for item in items:
                if len(collected) >= max_total_sentences:
                    break
                count_for_item = 0
                hits = retriever._text_search(
                    query_text=item,
                    limit=per_keyword * 2,
                    exclude_texts=used,
                    use_vector=True,
                    match_type="match",
                    require_all_words=True,
                )
                
                for hit in hits:
                    if count_for_item >= per_keyword or len(collected) >= max_total_sentences:
                        break
                    if is_duplicate(hit["text"], used, similarity_threshold=0.95):
                        continue
                    hit["parallels_item"] = item
                    hit["iteration"] = iteration
                    collected.append(_tag_sentence(hit, f"{label} ({item}) iter {iteration}", is_primary=False, parallels_section=section))
                    used.add(hit["text"])
                    count_for_item += 1
                    iteration_count += 1
                    total_collected += 1
            
            if iteration_count == 0:
                break
        
        return total_collected

    # Execute LOOP retrieval for each section (with early exit)
    logger.info(f"[Level 0.0] Starting searches (max {max_iterations} iters, cap {max_total_sentences} sentences)")
    
    stories_count = loop_vector_search(stories, per_iteration=5, label="Stories", section="stories_characters")
    refs_count = loop_vector_search(scripture_refs, per_iteration=3, label="Refs", section="scripture_references")
    metaphors_count = loop_keyword_vector_search(metaphors, per_iteration=3, label="Metaphors", section="biblical_metaphors")
    keywords_count = loop_keyword_search(keywords, per_keyword=2, label="Keywords", section="keywords")

    logger.info(f"[Level 0.0] Collected: {len(collected)} (S:{stories_count}, R:{refs_count}, M:{metaphors_count}, K:{keywords_count})")

    # Final dedup
    original_existing = set(existing_texts) if existing_texts else set()
    deduped, final_used = deduplicate_sentences(collected, existing_texts=original_existing, similarity_threshold=0.95)
    
    elapsed = time.time() - start_ts
    logger.info(f"[Level 0.0] Done in {elapsed:.2f}s with {len(deduped)} sentences")
    
    return deduped, used
