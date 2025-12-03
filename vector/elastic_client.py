# vector/elastic_client.py
from elasticsearch import Elasticsearch
from config import settings


def get_es_client():
    if settings.ES_USERNAME and settings.ES_PASSWORD:
        es = Elasticsearch(
            settings.ES_HOST,
            basic_auth=(settings.ES_USERNAME, settings.ES_PASSWORD),
            verify_certs=False,
        )
    else:
        es = Elasticsearch(settings.ES_HOST, verify_certs=False)
    return es


es = get_es_client()


def init_index():
    """
    Tạo index nếu chưa tồn tại.
    Mapping có:
    - text: câu gốc
    - level: level nguyên
    - embedding: dense_vector để search cosine
    """
    index_name = settings.ES_INDEX_NAME
    if es.indices.exists(index=index_name):
        return

    mapping = {
        "mappings": {
            "properties": {
                "text": {"type": "text"},
                "level": {"type": "integer"},
                "embedding": {
                    "type": "dense_vector",
                    "dims": 1536  # embedding size của OpenAI text-embedding-3-small
                }
            }
        }
    }

    es.indices.create(index=index_name, body=mapping)
    print(f"Created index: {index_name}")
