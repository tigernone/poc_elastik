# Search Logic Documentation

## Overview

This system uses a **Multi-Level Retrieval** approach to find relevant sentences from documents. When you ask a question like "Where is heaven?", the system:

1. **Extracts keywords** from your question (e.g., "heaven")
2. **Searches through 4 levels** to find the most relevant sentences
3. **Ranks results** using AI-powered vector similarity

---

## How It Works

### Step 1: Keyword Extraction

Your question is analyzed by AI to extract meaningful keywords:

| Question | Extracted Keywords |
|----------|-------------------|
| "Where is heaven?" | `["heaven"]` |
| "What is salvation?" | `["salvation"]` |
| "Why did Jesus die on the cross?" | `["Jesus", "cross", "die"]` |

**Filtered out**: Question words (where, what, why), common verbs (is, are, was), articles (the, a, an)

---

### Step 2: Multi-Level Search

The system searches through 4 levels progressively:

#### Level 0: Keyword Combinations
- **What it does**: Searches for sentences containing ALL keywords together
- **Example**: For keywords `["grace", "freedom"]` → searches "grace AND freedom"
- **Best for**: Finding highly specific matches

#### Level 1: Single Keyword Search  
- **What it does**: Searches for each keyword individually
- **Example**: `"heaven"` → finds ALL 56 sentences containing "heaven"
- **Limit**: Up to 50 sentences per keyword
- **Best for**: Comprehensive coverage of a topic

#### Level 2: Synonym Search
- **What it does**: AI generates synonyms and searches for them
- **Example**: `"heaven"` → `["paradise", "celestial realm", "sky"]`
- **Best for**: Finding related concepts with different wording

#### Level 3: Keyword + Context Words
- **What it does**: Combines keywords with context words (is, are, was, means, brings...)
- **Example**: `"heaven is"`, `"heaven was"`, `"heaven means"`
- **Search method**: Finds sentences containing BOTH words (not necessarily adjacent)
- **Best for**: Finding definitional or descriptive sentences

---

## Search Technology

### Text Search (Elasticsearch)
- **match**: Finds sentences containing the word(s)
- **match_phrase**: Finds exact phrases (words adjacent)
- **bool/must**: Requires ALL terms to be present

### Vector Search (AI Embeddings)
- Each sentence is converted to a 1536-dimension vector using OpenAI
- Your query is also converted to a vector
- **Cosine similarity** measures how "close" meanings are
- Higher score = more semantically relevant

### Combined Scoring
```
Final Score = Text Match × Vector Similarity
```

---

## Example: "Where is heaven?"

```
Query: "Where is heaven?"
     ↓
Keyword Extraction: ["heaven"]
     ↓
Level 0: Search "heaven" (combinations) → 0 results (only 1 keyword)
     ↓
Level 1: Search "heaven" → 56 sentences found
     ↓
Level 2: Search synonyms ["paradise", "celestial"] → additional sentences
     ↓
Level 3: Search "heaven is", "heaven was" → 13 sentences with both words
     ↓
Return top 15 sentences ranked by vector similarity
```

### Results Breakdown:
- **Total sentences with "heaven"**: 56
- **Sentences with "heaven" + "is"**: 13
- **Top results returned**: 15 (sorted by relevance score)

---

## "Tell Me More" Feature

When you click "Tell Me More":
1. System remembers previously shown sentences
2. Moves to next level or fetches more from current level
3. Never repeats the same sentence twice

---

## Score Interpretation

| Score Range | Meaning |
|-------------|---------|
| 8.0+ | Highly relevant - directly answers the question |
| 6.0-8.0 | Relevant - contains key concepts |
| 4.0-6.0 | Somewhat relevant - related topic |
| < 4.0 | Low relevance - loosely connected |

---

## Technical Stack

- **Elasticsearch**: Text search and document storage
- **OpenAI Embeddings**: text-embedding-3-small (1536 dimensions)
- **DeepSeek/GPT**: Keyword extraction and answer generation
- **FastAPI**: Backend API server
- **Streamlit**: Frontend UI
