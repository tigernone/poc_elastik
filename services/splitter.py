# services/splitter.py
from nltk.tokenize import sent_tokenize
import re


def clean_text(text: str) -> str:
    """Clean raw text before processing"""
    if not text:
        return ""
    
    # Remove BOM
    text = text.lstrip('\ufeff')
    
    # Normalize Windows line endings to Unix
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    
    # Replace smart quotes and special characters with ASCII equivalents
    replacements = {
        '\x93': '"', '\x94': '"',  # Smart double quotes (Windows-1252)
        '\x91': "'", '\x92': "'",  # Smart single quotes (Windows-1252)  
        '\x96': '-', '\x97': '-',  # En-dash, Em-dash
        '"': '"', '"': '"',        # Unicode smart double quotes
        ''': "'", ''': "'",        # Unicode smart single quotes
        '–': '-', '—': '-',        # Unicode dashes
        '…': '...',                # Ellipsis
        '\xa0': ' ',               # Non-breaking space
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    
    # Remove other control characters (except newlines and tabs)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)
    
    return text


def clean_sentence(text: str) -> str:
    """Clean a sentence: remove extra whitespace, control chars"""
    if not text:
        return ""
    # Remove control characters except newlines
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def split_into_sentences(text: str, split_mode: str = "auto") -> list[str]:
    """
    Split text into sentences.
    
    Args:
        text: Input text
        split_mode: 
            - "auto": Auto-detect (line-by-line if many lines, else NLTK)
            - "line": Split by newlines (for Bible, verse-per-line files)
            - "nltk": Use NLTK sentence tokenizer (for paragraphs)
    
    Returns:
        List of sentences
    """
    if not text or not text.strip():
        return []
    
    # Clean the text first
    text = clean_text(text)
    
    try:
        if split_mode == "line":
            # Split by newlines - each line is a sentence
            sentences = text.split('\n')
        elif split_mode == "nltk":
            # Use NLTK for paragraph-style text
            try:
                sentences = sent_tokenize(text)
            except Exception as e:
                print(f"[Splitter] NLTK failed: {e}, falling back to line mode")
                sentences = text.split('\n')
        else:
            # Auto-detect: if many short lines, use line mode
            lines = text.split('\n')
            non_empty_lines = [l.strip() for l in lines if l.strip()]
            
            # If average line length < 200 chars and > 100 lines, assume line-per-sentence format
            if non_empty_lines:
                avg_line_len = sum(len(l) for l in non_empty_lines) / len(non_empty_lines)
                if len(non_empty_lines) > 100 and avg_line_len < 200:
                    print(f"[Splitter] Auto-detected line-per-sentence format ({len(non_empty_lines)} lines, avg {avg_line_len:.0f} chars)")
                    sentences = non_empty_lines
                else:
                    print(f"[Splitter] Using NLTK sentence tokenizer")
                    try:
                        sentences = sent_tokenize(text)
                    except Exception as e:
                        print(f"[Splitter] NLTK failed: {e}, falling back to line mode")
                        sentences = non_empty_lines if non_empty_lines else text.split('\n')
            else:
                try:
                    sentences = sent_tokenize(text)
                except:
                    sentences = text.split('\n')
        
        # Clean and filter sentences
        cleaned = []
        for s in sentences:
            s = clean_sentence(s)
            # Only include sentences with at least 3 chars and some letters
            if s and len(s) >= 3 and re.search(r'[a-zA-Z]', s):
                cleaned.append(s)
        
        return cleaned
        
    except Exception as e:
        print(f"[Splitter] Error: {e}, using simple line split")
        # Ultimate fallback
        lines = text.split('\n')
        return [l.strip() for l in lines if l.strip() and len(l.strip()) >= 3]
