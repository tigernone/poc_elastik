# services/embedder.py
"""
Embedder Module - OpenAI embeddings
Hỗ trợ:
- Single text embedding
- Batch embedding (tối ưu cho nhiều text)
"""
from typing import List
from openai import OpenAI
from config import settings

client = OpenAI(api_key=settings.OPENAI_API_KEY)


def get_embedding(text: str) -> List[float]:
    """
    Lấy embedding cho một text.
    """
    resp = client.embeddings.create(
        model=settings.EMBEDDING_MODEL,
        input=text
    )
    return resp.data[0].embedding


def get_embeddings_batch(texts: List[str]) -> List[List[float]]:
    """
    Lấy embeddings cho nhiều texts cùng lúc.
    Hiệu quả hơn gọi từng text một.
    
    Args:
        texts: Danh sách các text cần embedding
        
    Returns:
        Danh sách các embeddings tương ứng
    """
    if not texts:
        return []
    
    # OpenAI API hỗ trợ batch embedding
    resp = client.embeddings.create(
        model=settings.EMBEDDING_MODEL,
        input=texts
    )
    
    # Sắp xếp theo index để đảm bảo thứ tự đúng
    embeddings = [None] * len(texts)
    for item in resp.data:
        embeddings[item.index] = item.embedding
    
    return embeddings
