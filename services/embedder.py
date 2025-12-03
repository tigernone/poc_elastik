# services/embedder.py
"""
Embedder Module - OpenAI Embeddings API
Sử dụng EMBEDDING_API_KEY để gọi OpenAI embedding API
"""
from typing import List
from openai import OpenAI
from config import settings

# Initialize OpenAI client with EMBEDDING_API_KEY
print("Initializing OpenAI Embedding client...")
client = OpenAI(api_key=settings.EMBEDDING_API_KEY)
EMBEDDING_MODEL = settings.EMBEDDING_MODEL  # text-embedding-3-small
print(f"OpenAI Embedding ready! Model: {EMBEDDING_MODEL}")


def get_embedding(text: str) -> List[float]:
    """
    Lấy embedding cho một text sử dụng OpenAI API.
    """
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text
    )
    return response.data[0].embedding


def get_embeddings_batch(texts: List[str]) -> List[List[float]]:
    """
    Lấy embeddings cho nhiều texts cùng lúc.
    OpenAI API hỗ trợ batch embedding.
    
    Args:
        texts: Danh sách các text cần embedding
        
    Returns:
        Danh sách các embeddings tương ứng
    """
    if not texts:
        return []
    
    # OpenAI supports batch embedding
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=texts
    )
    
    # Sort by index to maintain order
    sorted_data = sorted(response.data, key=lambda x: x.index)
    return [item.embedding for item in sorted_data]
