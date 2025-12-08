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
    """Generate detailed keyword meaning in the context of Bible and Ellen G. White's writings"""
    prompt = f"""What is the detailed meaning, in both the Bible and Ellen G. White's writings, of the prayer: "{query}", specifically for understanding the model needed to write a sermon?

Provide a comprehensive explanation covering:
1. Biblical context and references
2. Ellen G. White's perspective on this topic
3. How this applies to sermon writing
4. Key theological insights

Be thorough and spiritually insightful."""
    
    try:
        response = client.chat.completions.create(
            model=settings.CHAT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=800
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Error generating meaning: {str(e)}"

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
    
    # Use custom_prompt if provided, otherwise use default
    if custom_prompt:
        prompt = f"""{custom_prompt}

QUESTION: {user_query}

MEANING: {keyword_meaning}

{vector_section}{keyword_section}"""
    else:
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
            max_tokens=settings.LLM_MAX_TOKENS  # Use config value (8000)
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Error: {str(e)}"
