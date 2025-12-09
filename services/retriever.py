# services/retriever.py
"""
Retriever Module - Multi-level retrieval for Q&A
Supports:
- Level-based retrieval (Level 0, 1, 2...)
- Buffer 10-20% when retrieving sentences
- Exclude previously used sentences
- Deduplicate
- Batch processing to prevent RAM overflow
"""
from typing import List, Dict, Any, Set, Optional, Generator
from vector.elastic_client import es
from config import settings
from services.embedder import get_embedding, get_embeddings_batch
from services.deduplicator import is_duplicate, deduplicate_sentences

INDEX = settings.ES_INDEX_NAME

# Constants
DEFAULT_SENTENCES_PER_LEVEL = 5
MAX_BATCH_SIZE = 500  # Batch size for embedding (OpenAI supports up to 2048)


def index_sentences_batch(
    sentences: List[str], 
    file_id: str = None,
    sentences_per_level: int = DEFAULT_SENTENCES_PER_LEVEL,
    batch_size: int = MAX_BATCH_SIZE
) -> int:
    """
    Index list of sentences into Elasticsearch with batch processing.
    Prevents RAM overflow by processing in batches.
    
    Args:
        sentences: List of sentences
        file_id: File ID
        sentences_per_level: Number of sentences per level
        batch_size: Batch size for processing
    
    Returns: max_level created
    """
    max_level = 0
    total_sentences = len(sentences)
    total_batches = (total_sentences + batch_size - 1) // batch_size
    
    print(f"[Indexer] Starting to index {total_sentences} sentences in {total_batches} batches (batch_size={batch_size})")
    
    # Xử lý từng batch
    for batch_start in range(0, total_sentences, batch_size):
        batch_end = min(batch_start + batch_size, total_sentences)
        batch_sentences = sentences[batch_start:batch_end]
        batch_num = batch_start // batch_size + 1
        print(f"[Indexer] Processing batch {batch_num}/{total_batches} ({batch_start+1}-{batch_end} of {total_sentences})")
        
        # Lấy embeddings cho cả batch (tối ưu hơn gọi từng câu)
        embeddings = get_embeddings_batch(batch_sentences)
        
        actions = []
        for i, (sent, emb) in enumerate(zip(batch_sentences, embeddings)):
            global_index = batch_start + i
            level = global_index // sentences_per_level
            max_level = max(max_level, level)
            
            doc = {
                "text": sent,
                "level": level,
                "embedding": emb,
                "sentence_index": global_index,
            }
            
            if file_id:
                doc["file_id"] = file_id
            
            actions.append({"index": {"_index": INDEX}})
            actions.append(doc)
        
        if actions:
            es.bulk(body=actions, refresh=True)
    
    return max_level


def index_sentences(
    sentences: List[str], 
    file_id: str = None,
    sentences_per_level: int = DEFAULT_SENTENCES_PER_LEVEL
) -> int:
    """
    Index danh sách câu vào Elasticsearch.
    Wrapper cho index_sentences_batch với batch processing.
    """
    return index_sentences_batch(
        sentences=sentences,
        file_id=file_id,
        sentences_per_level=sentences_per_level,
        batch_size=MAX_BATCH_SIZE
    )


def get_max_level() -> int:
    """Lấy level cao nhất có trong index"""
    try:
        body = {
            "size": 0,
            "aggs": {
                "max_level": {"max": {"field": "level"}}
            }
        }
        resp = es.search(index=INDEX, body=body)
        max_val = resp["aggregations"]["max_level"]["value"]
        return int(max_val) if max_val else 0
    except Exception:
        return 0


def knn_search(
    query: str, 
    top_k: int = 30,
    target_levels: List[int] = None,
    exclude_texts: Set[str] = None
) -> List[Dict[str, Any]]:
    """
    Tìm các câu gần nhất bằng cosineSimilarity + phrase proximity boost.
    
    Args:
        query: Câu hỏi của user
        top_k: Số kết quả tối đa
        target_levels: Chỉ lấy từ các level này (None = tất cả)
        exclude_texts: Các câu đã dùng, cần loại bỏ
    
    Returns: list [{text, level, score}, ...]
    """
    query_vec = get_embedding(query)
    
    # Build query với filter nếu cần
    must_clauses = []
    must_not_clauses = []
    
    if target_levels is not None:
        must_clauses.append({
            "terms": {"level": target_levels}
        })
    
    if exclude_texts:
        for text in exclude_texts:
            must_not_clauses.append({
                "match_phrase": {"text": text}
            })
    
    # Build bool query
    if must_clauses or must_not_clauses:
        bool_query = {"bool": {}}
        if must_clauses:
            bool_query["bool"]["must"] = must_clauses
        if must_not_clauses:
            bool_query["bool"]["must_not"] = must_not_clauses
        inner_query = bool_query
    else:
        inner_query = {"match_all": {}}

    # Main query: Vector similarity + Phrase matching boost
    body = {
        "size": top_k * 2,  # Lấy nhiều hơn để re-rank
        "query": {
            "script_score": {
                "query": inner_query,
                "script": {
                    "source": "cosineSimilarity(params.query_vector, 'embedding') + 1.0",
                    "params": {"query_vector": query_vec}
                }
            }
        }
    }

    resp = es.search(index=INDEX, body=body)

    # Collect results and calculate phrase proximity boost
    results = []
    for hit in resp["hits"]["hits"]:
        src = hit["_source"]
        text = src["text"]
        base_score = hit["_score"]
        
        # Calculate phrase proximity boost
        phrase_boost = calculate_phrase_proximity_boost(query, text)
        
        # Final score = base_score * (1 + phrase_boost)
        final_score = base_score * (1 + phrase_boost)
        
        results.append({
            "text": text,
            "level": src.get("level", 0),
            "score": final_score,
            "sentence_index": src.get("sentence_index", 0),
            "base_score": base_score,
            "phrase_boost": phrase_boost
        })
    
    # Re-rank by final score
    results.sort(key=lambda x: -x["score"])
    
    # Return top_k
    return results[:top_k]


def calculate_phrase_proximity_boost(query: str, text: str) -> float:
    """
    Tính boost dựa trên độ gần nhau của các từ trong query.
    
    Nếu các từ xuất hiện gần nhau trong text thì boost cao hơn.
    Ví dụ: query="heaven is" -> "heaven is" (liền kề) được boost cao nhất
    
    Returns: boost value (0.0 to 2.0)
    """
    import re
    
    query_lower = query.lower().strip()
    text_lower = text.lower()
    
    # Split query into words (remove punctuation)
    query_words = re.findall(r'\b\w+\b', query_lower)
    
    if len(query_words) <= 1:
        # Single word query, no proximity boost needed
        return 0.0
    
    # Check if exact phrase exists (with flexible whitespace/punctuation)
    # Build regex pattern: word1\s+word2 or word1[^\w]+word2
    pattern = r'\b' + r'\s+'.join(re.escape(w) for w in query_words) + r'\b'
    if re.search(pattern, text_lower):
        return 2.0  # Maximum boost for exact consecutive phrase
    
    # Tokenize text into words
    text_words = re.findall(r'\b\w+\b', text_lower)
    
    # Find all positions of each query word in text
    word_positions = {}
    for query_word in query_words:
        positions = []
        for i, text_word in enumerate(text_words):
            if text_word == query_word:  # Exact match only
                positions.append(i)
        if positions:
            word_positions[query_word] = positions
    
    # If not all query words are found, no boost
    if len(word_positions) < len(query_words):
        return 0.0
    
    # Calculate minimum distance between consecutive query words in order
    # Try all combinations of positions
    from itertools import product
    
    position_combinations = [word_positions[w] for w in query_words]
    min_avg_distance = float('inf')
    
    for combo in product(*position_combinations):
        # combo is a tuple of positions for each query word
        # Check if words appear in correct order
        in_order = all(combo[i] < combo[i+1] for i in range(len(combo) - 1))
        
        if not in_order:
            continue
        
        # Calculate total distance
        total_distance = 0
        for i in range(len(combo) - 1):
            distance = combo[i+1] - combo[i] - 1  # -1 because consecutive = distance 0
            total_distance += distance
        
        # Average distance per word pair
        avg_distance = total_distance / (len(combo) - 1) if len(combo) > 1 else 0
        min_avg_distance = min(min_avg_distance, avg_distance)
    
    if min_avg_distance == float('inf'):
        return 0.0
    
    # Boost calculation: closer = higher boost
    # Consecutive words (distance=0) get highest boost
    if min_avg_distance == 0:
        boost = 2.0  # Consecutive words
    elif min_avg_distance <= 1:
        boost = 1.5  # 1 word in between
    elif min_avg_distance <= 2:
        boost = 1.0  # 2 words in between
    elif min_avg_distance <= 3:
        boost = 0.6  # 3 words in between
    elif min_avg_distance <= 5:
        boost = 0.3  # 4-5 words in between
    else:
        boost = 0.1  # Far apart
    
    return boost


def get_sentences_by_level(
    query: str,
    start_level: int = 0,
    end_level: int = None,
    limit: int = 15,
    exclude_texts: Set[str] = None,
    buffer_percentage: int = 15
) -> List[Dict[str, Any]]:
    """
    Lấy câu nguồn từ các level cụ thể với buffer.
    Dùng cho "Tell me more" - đi sâu vào level tiếp theo.
    
    Args:
        query: Câu hỏi
        start_level: Level bắt đầu
        end_level: Level kết thúc (None = tất cả từ start_level trở đi)
        limit: Số câu tối đa cơ bản
        exclude_texts: Các câu đã dùng
        buffer_percentage: Buffer % thêm (10-20%)
    
    Returns: Danh sách câu đã dedupe, group theo level
    """
    # Áp dụng buffer (10-20%)
    buffer_pct = max(10, min(20, buffer_percentage))  # Clamp 10-20%
    buffered_limit = int(limit * (1 + buffer_pct / 100))
    
    max_level = get_max_level()
    
    if end_level is None:
        end_level = max_level
    
    # Tạo list các level cần query
    target_levels = list(range(start_level, end_level + 1))
    
    if not target_levels:
        return []
    
    # Search - lấy nhiều hơn để đủ sau khi dedupe
    hits = knn_search(
        query=query,
        top_k=buffered_limit * 3,
        target_levels=target_levels,
        exclude_texts=exclude_texts
    )
    
    # Deduplicate with advanced similarity checking
    seen = set()
    unique = []
    for h in hits:
        t = h["text"]
        # Check with similarity-based deduplication (90% threshold)
        if is_duplicate(t, seen, similarity_threshold=0.90):
            continue
        if exclude_texts and is_duplicate(t, exclude_texts, similarity_threshold=0.90):
            continue
        seen.add(t)
        unique.append(h)
        if len(unique) >= buffered_limit:  # Dùng buffered_limit
            break
    
    # Sort theo level, rồi score giảm dần
    unique.sort(key=lambda x: (x["level"], -x["score"]))
    
    return unique


def get_top_unique_sentences_grouped(
    query: str, 
    limit: int = 15,
    exclude_texts: Set[str] = None,
    buffer_percentage: int = 15
) -> List[Dict[str, Any]]:
    """
    Lấy câu nguồn cho câu hỏi đầu tiên (Level 0 là chính).
    Áp dụng buffer 10-20%.
    1. Search theo embedding
    2. Lấy unique text
    3. Áp dụng buffer
    4. Group theo level, sort theo level rồi score
    """
    return get_sentences_by_level(
        query=query,
        start_level=0,
        end_level=None,  # Lấy từ tất cả level nhưng ưu tiên level thấp
        limit=limit,
        exclude_texts=exclude_texts,
        buffer_percentage=buffer_percentage
    )


def delete_all_documents():
    """Xóa tất cả documents trong index"""
    try:
        es.delete_by_query(
            index=INDEX,
            body={"query": {"match_all": {}}}
        )
        return True
    except Exception:
        return False


def delete_documents_by_file(file_id: str):
    """Xóa documents theo file_id"""
    try:
        es.delete_by_query(
            index=INDEX,
            body={"query": {"term": {"file_id": file_id}}}
        )
        return True
    except Exception:
        return False


def get_document_count() -> int:
    """Đếm số documents trong index"""
    try:
        resp = es.count(index=INDEX)
        return resp["count"]
    except Exception:
        return 0
