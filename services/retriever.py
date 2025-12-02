# services/retriever.py
"""
Retriever Module - Multi-level retrieval cho Q&A
Hỗ trợ:
- Level-based retrieval (Level 0, 1, 2...)
- Buffer 10-20% khi lấy câu
- Exclude các câu đã dùng
- Deduplicate
- Batch processing để tránh tràn RAM
"""
from typing import List, Dict, Any, Set, Optional, Generator
from vector.elastic_client import es
from config import settings
from services.embedder import get_embedding, get_embeddings_batch

INDEX = settings.ES_INDEX_NAME

# Constants
DEFAULT_SENTENCES_PER_LEVEL = 5
MAX_BATCH_SIZE = 50  # Batch size cho embedding để tránh tràn RAM


def index_sentences_batch(
    sentences: List[str], 
    file_id: str = None,
    sentences_per_level: int = DEFAULT_SENTENCES_PER_LEVEL,
    batch_size: int = MAX_BATCH_SIZE
) -> int:
    """
    Index danh sách câu vào Elasticsearch với batch processing.
    Tránh tràn RAM bằng cách xử lý từng batch.
    
    Args:
        sentences: Danh sách câu
        file_id: ID của file
        sentences_per_level: Số câu mỗi level
        batch_size: Kích thước batch để xử lý
    
    Returns: max_level được tạo
    """
    max_level = 0
    total_sentences = len(sentences)
    
    # Xử lý từng batch
    for batch_start in range(0, total_sentences, batch_size):
        batch_end = min(batch_start + batch_size, total_sentences)
        batch_sentences = sentences[batch_start:batch_end]
        
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
    Tìm các câu gần nhất bằng cosineSimilarity.
    
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

    body = {
        "size": top_k,
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

    results = []
    for hit in resp["hits"]["hits"]:
        src = hit["_source"]
        results.append({
            "text": src["text"],
            "level": src.get("level", 0),
            "score": hit["_score"],
            "sentence_index": src.get("sentence_index", 0)
        })
    return results


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
    
    # Deduplicate
    seen = set()
    unique = []
    for h in hits:
        t = h["text"]
        if t not in seen and (exclude_texts is None or t not in exclude_texts):
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
