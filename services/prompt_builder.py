# services/prompt_builder.py
"""Prompt Builder - Creates structured prompts for LLM"""
from typing import List, Dict, Any
from config import settings
from openai import OpenAI

if settings.DEEPSEEK_BASE_URL:
    client = OpenAI(api_key=settings.DEEPSEEK_API_KEY, base_url=settings.DEEPSEEK_BASE_URL)
else:
    client = OpenAI(api_key=settings.DEEPSEEK_API_KEY)

def generate_question_variants(query: str, previous_variants: List[str] = None, continue_mode: bool = False) -> str:
    return f"Variants of: {query}"

def extract_keywords(query: str, previous_keywords: str = None, continue_mode: bool = False) -> str:
    return f"Keywords from: {query}"

def build_final_prompt(user_query: str, question_variants: str, keyword_meaning: str, source_sentences: List[Dict[str, Any]], continue_mode: bool = False, continue_count: int = 0, custom_prompt: str = None) -> str:
    vector_sources = [s for s in source_sentences if s.get("is_primary_source", False)]
    keyword_sources = [s for s in source_sentences if not s.get("is_primary_source", False)]
    
    vector_section = ""
    if vector_sources:
        vector_section = "\n## PRIMARY SOURCES (Vector/Semantic):\n"
        for i, sent in enumerate(vector_sources, 1):
            vector_section += f"{i}. {sent['text']}\n"
    
    keyword_section = ""
    if keyword_sources:
        keyword_section = "\n## SECONDARY SOURCES (Keyword Match):\n"
        for i, sent in enumerate(keyword_sources, 1):
            keyword_section += f"{i}. {sent['text']}\n"
    
    prompt = f"""Answer based on sources below.

QUESTION: {user_query}

{vector_section}{keyword_section}

INSTRUCTIONS:
1. Prioritize PRIMARY sources (vector search)
2. Use SECONDARY sources as supporting evidence
3. Be accurate and concise

ANSWER:"""
    
    return prompt

def call_llm(prompt: str) -> str:
    try:
        response = client.chat.completions.create(
            model=settings.CHAT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=1000
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Error: {str(e)}"
