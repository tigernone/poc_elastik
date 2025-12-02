# services/prompt_builder.py
"""
Prompt Builder Module - Xây dựng prompt có cấu trúc cho LLM
Theo yêu cầu khách:
- Question variations (3-4 biến thể)
- Keyword meaning
- Source sentences (group theo level)
- Instructions
"""
from typing import List, Dict, Optional
from openai import OpenAI
from config import settings

client = OpenAI(api_key=settings.OPENAI_API_KEY)


def generate_question_variants(
    user_query: str, 
    previous_variants: List[str] = None,
    continue_mode: bool = False
) -> str:
    """
    Tạo 3–4 phiên bản câu hỏi khác nhau.
    
    Args:
        user_query: Câu hỏi gốc
        previous_variants: Các biến thể đã dùng trước đó (để tránh lặp)
        continue_mode: Nếu True, tạo biến thể mới không lặp lại
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
    
    resp = client.chat.completions.create(
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
    Extract keywords / meaning mô tả.
    
    Args:
        user_query: Câu hỏi gốc
        previous_keywords: Keywords đã giải thích trước đó
        continue_mode: Nếu True, tìm keywords mới/sâu hơn
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
    
    resp = client.chat.completions.create(
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
    Build prompt đầy đủ theo cấu trúc yêu cầu.
    
    Args:
        user_query: Câu hỏi gốc
        question_variants: Các biến thể câu hỏi
        keyword_meaning: Giải nghĩa keywords
        source_sentences: Danh sách câu nguồn (đã group theo level)
        continue_mode: Đang ở chế độ "Tell me more"
        continue_count: Số lần đã bấm Continue
        custom_prompt: Custom instructions từ user (optional)
    """
    # Build source sentences block, group theo level
    src_lines = []
    current_level = None
    for s in source_sentences:
        lvl = s["level"]
        if current_level != lvl:
            current_level = lvl
            src_lines.append(f"\n[Level {lvl} sentences]")
        src_lines.append(f"- {s['text']}")

    src_block = "\n".join(src_lines)
    
    # Instructions khác nhau cho lần đầu và continue
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
    """Gọi LLM để sinh câu trả lời"""
    resp = client.chat.completions.create(
        model=settings.CHAT_MODEL,
        messages=[{"role": "user", "content": prompt}]
    )
    return resp.choices[0].message.content.strip()
