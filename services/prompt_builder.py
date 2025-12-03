# services/prompt_builder.py
"""
Prompt Builder Module - Build structured prompts for LLM
As per client requirements:
- Question variations (3-4 variants)
- Keyword meaning
- Source sentences (grouped by level)
- Instructions
"""
from typing import List, Dict, Optional
from openai import OpenAI
from config import settings

# Chat client (DeepSeek or OpenAI)
if settings.OPENAI_BASE_URL:
    chat_client = OpenAI(
        api_key=settings.OPENAI_API_KEY,
        base_url=settings.OPENAI_BASE_URL
    )
else:
    chat_client = OpenAI(api_key=settings.OPENAI_API_KEY)


def generate_question_variants(
    user_query: str, 
    previous_variants: List[str] = None,
    continue_mode: bool = False
) -> str:
    """
    Generate 3-4 different versions of the question.
    
    Args:
        user_query: Original question
        previous_variants: Previously used variants (to avoid repetition)
        continue_mode: If True, generate new variants without repeating
    """
    if continue_mode and previous_variants:
        previous_text = "\n".join(previous_variants)
        prompt = (
            f"The user asked: \"{user_query}\"\n\n"
            f"Previously generated variations (DO NOT repeat these):\n{previous_text}\n\n"
            "Generate 3-4 NEW and DIFFERENT variations of this question. "
            "Focus on asking for more details, deeper explanation, or related aspects. "
            "Each variation on a new line:"
        )
    else:
        prompt = (
            "Rewrite the following question in 3-4 different ways, "
            "each on a new line:\n\n"
            f"{user_query}"
        )
    
    resp = chat_client.chat.completions.create(
        model=settings.CHAT_MODEL,
        messages=[{"role": "user", "content": prompt}]
    )
    return resp.choices[0].message.content.strip()


def extract_keywords(
    user_query: str,
    previous_keywords: List[str] = None,
    continue_mode: bool = False
) -> str:
    """
    Extract keywords and their meanings.
    
    Args:
        user_query: Original question
        previous_keywords: Previously explained keywords
        continue_mode: If True, find new/deeper keywords
    """
    if continue_mode and previous_keywords:
        previous_text = "\n".join(previous_keywords)
        prompt = (
            f"The user is exploring the question: \"{user_query}\"\n\n"
            f"Previously explained keywords:\n{previous_text}\n\n"
            "Now extract NEW or more SPECIFIC keywords that haven't been covered. "
            "Focus on deeper concepts, related terms, or technical details. "
            "Answer in 2-3 short sentences:"
        )
    else:
        prompt = (
            "Extract the main keywords and briefly explain their meaning "
            "from this question. Answer in 2-3 short sentences:\n\n"
            f"{user_query}"
        )
    
    resp = chat_client.chat.completions.create(
        model=settings.CHAT_MODEL,
        messages=[{"role": "user", "content": prompt}]
    )
    return resp.choices[0].message.content.strip()


def build_final_prompt(
    user_query: str,
    question_variants: str,
    keyword_meaning: str,
    source_sentences: List[Dict],
    continue_mode: bool = False,
    continue_count: int = 0,
    custom_prompt: Optional[str] = None
) -> str:
    """
    Build full prompt according to required structure.
    
    Args:
        user_query: Original question
        question_variants: Question variants
        keyword_meaning: Keyword explanations
        source_sentences: List of source sentences (grouped by level)
        continue_mode: In "Tell me more" mode
        continue_count: Number of times Continue was clicked
        custom_prompt: Custom instructions from user (optional)
    """
    # Build source sentences block, grouped by level
    src_lines = []
    current_level = None
    for s in source_sentences:
        lvl = s["level"]
        if current_level != lvl:
            current_level = lvl
            src_lines.append(f"\n[Level {lvl} sentences]")
        src_lines.append(f"- {s['text']}")

    src_block = "\n".join(src_lines)
    
    # Different instructions for first time vs continue
    if continue_mode:
        instructions = f"""
Instructions:
- This is a FOLLOW-UP request (Continue #{continue_count}).
- The user wants MORE DETAILS and DEEPER information.
- Use ONLY the NEW source sentences above (from deeper levels) to EXPAND the answer.
- DO NOT simply repeat previous information.
- Focus on new insights, additional details, and deeper explanations.
- If no new information is available, clearly state that all available information has been provided.
"""
    else:
        instructions = """
Instructions:
- Use ONLY the information in the source sentences to answer.
- If you cannot find the answer, say you don't have enough information.
- Answer clearly and concisely.
- Group your answer logically based on the source levels if applicable.
"""

    # Add custom prompt from user if provided
    custom_section = ""
    if custom_prompt and custom_prompt.strip():
        custom_section = f"""
User custom instructions:
{custom_prompt.strip()}
"""

    final_prompt = f"""
User original question:
{user_query}

Question variations:
{question_variants}

Keyword meaning:
{keyword_meaning}

Source sentences (grouped by level):
{src_block}
{instructions}{custom_section}
"""
    return final_prompt.strip()


def call_llm(prompt: str) -> str:
    """Call LLM to generate answer"""
    resp = chat_client.chat.completions.create(
        model=settings.CHAT_MODEL,
        messages=[{"role": "user", "content": prompt}]
    )
    return resp.choices[0].message.content.strip()
