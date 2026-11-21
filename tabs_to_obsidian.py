#!/usr/bin/env python3
"""
tabs_to_obsidian.py — LLM reading queue with a RELATIONSHIP GRAPH.

Turns browser tabs into Obsidian notes. A local LLM (llama-server / Ollama /
LM Studio, OpenAI-compatible API) performs two passes:

  1. DESCRIPTION pass: English, 60-120 word description + topic tags + level.
  2. RELATIONSHIP pass: for every note, which notes are prerequisites and which
     are related. The result is a directed graph, a topological learning path,
     and note-to-note wikilinks that Obsidian's Graph view renders as edges.

No external Python dependencies. Python 3.8+.
"""

from __future__ import annotations

import argparse
import hashlib
import heapq
import html
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

SCRIPT_DIR = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# Taxonomy (English). Edit topics.json to customize.
# ---------------------------------------------------------------------------
DEFAULT_TOPICS = {
    "Transformers & Attention": {
        "tag": "transformers",
        "keywords": ["transformer", "attention", "self-attention", "multi-head",
                     "positional encoding", "bert", "gpt", "flash attention"],
    },
    "RAG": {
        "tag": "rag",
        "keywords": ["rag", "retrieval", "retrieval-augmented", "vector database",
                     "dense retrieval", "bm25", "reranker", "chunking", "pinecone"],
    },
    "Fine-tuning & PEFT": {
        "tag": "fine-tuning",
        "keywords": ["fine-tuning", "fine tuning", "finetuning", "fine-tune",
                     "lora", "qlora", "peft", "adapter", "instruction tuning",
                     "sft", "dpo", "smol training"],
    },
    "Prompting": {
        "tag": "prompting",
        "keywords": ["prompt engineering", "chain of thought", "few-shot",
                     "zero-shot", "prompting", "prompt", "cot"],
    },
    "Agents & Tools": {
        "tag": "agents",
        "keywords": ["agent", "agentic", "tool use", "function calling", "langchain",
                     "autogpt", "toolformer", "mcp", "multi-agent"],
    },
    "Evaluation & Benchmarks": {
        "tag": "evaluation",
        "keywords": ["benchmark", "evaluation", "evals", "eval", "leaderboard",
                     "mmlu", "humaneval", "gsm8k", "metric", "mlperf"],
    },
    "RLHF & Alignment": {
        "tag": "alignment",
        "keywords": ["rlhf", "alignment", "safety", "reward model", "ppo",
                     "instructgpt", "red team", "guardrail", "jailbreak"],
    },
    "Inference & Optimization": {
        "tag": "inference",
        "keywords": ["quantization", "inference", "serving", "vllm", "gguf",
                     "llama.cpp", "latency", "throughput", "distillation",
                     "kv cache", "speculative decoding", "mixture-of-experts"],
    },
    "Embeddings": {
        "tag": "embeddings",
        "keywords": ["embedding", "embeddings", "sentence-transformers",
                     "cosine similarity", "text-embedding", "vector representation"],
    },
    "Multimodal": {
        "tag": "multimodal",
        "keywords": ["multimodal", "vision language", "clip", "gpt-4v", "whisper",
                     "image", "video", "audio", "speech"],
    },
    "Training & Scaling": {
        "tag": "training",
        "keywords": ["pretraining", "pre-training", "training", "scaling law",
                     "compute", "dataset", "data pipeline", "distributed",
                     "deepspeed", "megatron", "scaling transformers"],
    },
    "Reasoning": {
        "tag": "reasoning",
        "keywords": ["reasoning", "o1", "o3", "deepseek-r1", "math", "logic",
                     "chain-of-thought"],
    },
    "Tokenization": {
        "tag": "tokenization",
        "keywords": ["tokenization", "tokenisation", "tokenizer",
                     "byte pair encoding", "bpe", "sentencepiece", "vocab"],
    },
    "Context & Memory": {
        "tag": "context",
        "keywords": ["long context", "context window", "context length", "memory",
                     "longformer", "ring attention", "needle in a haystack"],
    },
    "Open Models": {
        "tag": "open-models",
        "keywords": ["llama", "mistral", "qwen", "gemma", "open weights",
                     "open-source model", "open source llm"],
    },
    "Interpretability": {
        "tag": "interpretability",
        "keywords": ["interpretability", "mechanistic interpretability", "neurons",
                     "features", "circuits", "activation", "probing", "transparency"],
    },
    "Deep Learning Fundamentals": {
        "tag": "deep-learning",
        "keywords": ["backpropagation", "backprop", "gradient descent", "lenet",
                     "mnist", "activation function", "normalizing flow", "neural network",
                     "approximation theory", "optimization", "convolution"],
    },
    "NLP Foundations": {
        "tag": "nlp",
        "keywords": ["natural language processing", "nlp", "language model",
                     "sequence", "linguistics", "pos tagging", "machine translation"],
    },
    "Interview Prep": {
        "tag": "interview",
        "keywords": ["interview", "questions and answers", "must-know", "leetcode",
                     "take-home", "assignment", "syllabus", "course"],
    },
    "General": {
        "tag": "general",
        "keywords": [],
    },
}

STATUSES = ["queued", "reading", "read", "archived"]
PRIORITIES = ["high", "medium", "low"]
STATUS_LABEL = {
    "queued": "To read", "reading": "Reading", "read": "Read", "archived": "Archived",
}

EXAMPLE_TABS = {
    "exported_at": "2026-11-21T12:00:00Z", "source": "example",
    "tabs": [
        {"title": "Attention Is All You Need", "url": "https://arxiv.org/abs/1706.03762"},
        {"title": "Retrieval-Augmented Generation for Knowledge-Intensive NLP",
         "url": "https://arxiv.org/abs/2005.11401"},
        {"title": "LoRA: Low-Rank Adaptation of Large Language Models",
         "url": "https://arxiv.org/abs/2106.09685"},
        {"title": "Chain-of-Thought Prompting Elicits Reasoning in LLMs",
         "url": "https://arxiv.org/abs/2201.11903"},
        {"title": "vLLM: Efficient Memory Management for LLM Serving",
         "url": "https://arxiv.org/abs/2309.06180"},
        {"title": "Training language models to follow instructions with human feedback",
         "url": "https://arxiv.org/abs/2203.02155"},
        {"title": "DeepSeek-R1: Incentivizing Reasoning Capability via RL",
         "url": "https://arxiv.org/abs/2501.12948"},
        {"title": "Building effective agents",
         "url": "https://www.anthropic.com/research/building-effective-agents"},
        {"title": "The Illustrated Transformer",
         "url": "https://jalammar.github.io/illustrated-transformer/"},
    ],
}


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------
def slugify(text: str, max_len: int = 60) -> str:
    text = (text or "").lower()
    text = re.sub(r"[^a-z0-9áéíóúüñ]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text[:max_len].strip("-") or "untitled"


def normalize_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    parsed = urlparse(url)
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{parsed.path.rstrip('/')}"


def url_hash(url: str) -> str:
    return hashlib.sha1(normalize_url(url).encode("utf-8")).hexdigest()[:8]


def infer_source(url: str) -> str:
    host = urlparse(url if re.match(r"^https?://", url) else "https://" + url).netloc.lower()
    papers = ("arxiv.org", "aclanthology.org", "openreview.net", "biorxiv.org",
              "nature.com", "sciencedirect.com", "jmlr.org", "proceedings.mlr.press",
              "papers.nips.cc", "researchgate.net")
    if any(h in host for h in papers):
        return "paper"
    if any(h in host for h in ("github.com", "huggingface.co")):
        return "code"
    return "blog"


def classify(title: str, url: str, topics: dict, max_topics: int) -> list[str]:
    text = f"{title} {url}"
    scored = []
    for name, cfg in topics.items():
        score = sum(1 for kw in cfg.get("keywords", [])
                    if re.search(r"\b" + re.escape(kw) + r"\b", text, re.I))
        if score:
            scored.append((score, list(topics).index(name), name))
    scored.sort(reverse=True)
    return [name for _, _, name in scored[:max_topics]] or ["General"]


def parse_value(raw: str):
    raw = (raw or "").strip()
    if not raw:
        return ""
    if raw[0] in "\"'" and raw[-1] == raw[0]:
        try:
            return json.loads(raw)
        except Exception:
            return raw.strip("\"'")
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        if not inner:
            return []
        parts = re.split(r',\s*(?=(?:[^"]*"[^"]*")*[^"]*$)', inner)
        return [parse_value(p) for p in parts]
    if re.fullmatch(r"true|false", raw, re.I):
        return raw.lower() == "true"
    if re.fullmatch(r"-?\d+", raw):
        return int(raw)
    return raw


def yaml_value(v) -> str:
    if isinstance(v, list):
        return "[" + ", ".join(json.dumps(str(x), ensure_ascii=False) for x in v) + "]"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    return json.dumps(str(v), ensure_ascii=False)


def split_frontmatter(text: str):
    if not text.startswith("---"):
        return {}, text
    match = re.search(r"(?m)^---[ \t]*$", text[4:])
    if not match:
        return {}, text
    fm_text = text[4:4 + match.start()]
    body = text[4 + match.end():].lstrip("\n")
    fields = {}
    for line in fm_text.splitlines():
        m = re.match(r"^([A-Za-z_][\w-]*):[ \t]*(.*)$", line)
        if m:
            fields[m.group(1)] = parse_value(m.group(2))
    return fields, body


def render_note(fields: dict, body: str) -> str:
    return ("---\n" + "".join(f"{k}: {yaml_value(v)}\n" for k, v in fields.items())
            + "---\n\n" + body.lstrip("\n"))


def today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_tabs(path: Path) -> list[dict]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    suffix = path.suffix.lower()
    if suffix == ".json":
        data = json.loads(raw)
        tabs = data.get("tabs", data) if isinstance(data, dict) else data
        if isinstance(tabs, dict):
            tabs = [tabs]
        return [t for t in tabs if isinstance(t, dict) and t.get("url")]
    if suffix in (".txt", ".md"):
        out = []
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            title = None
            if " | " in line:
                title, line = [p.strip() for p in line.split(" | ", 1)]
            if not re.match(r"^https?://", line, re.I):
                line = "https://" + line
            out.append({"title": title or line, "url": line})
        return out
    if suffix in (".html", ".htm"):
        out = []
        for href, label in re.findall(r"<a\s+[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>",
                                      raw, re.I | re.S):
            title = html.unescape(re.sub(r"<[^>]+>", "", label)).strip()
            if href.startswith("http"):
                out.append({"title": title or href, "url": href})
        return out
    raise ValueError(f"Unsupported format: {suffix}. Use .json, .txt or .html")


def load_topics(path: str | None) -> dict:
    p = Path(path) if path else (SCRIPT_DIR / "topics.json")
    if p.exists():
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data:
            return data
    return DEFAULT_TOPICS


# ---------------------------------------------------------------------------
# Local model
# ---------------------------------------------------------------------------
LLM_SYSTEM = (
    "You are a research librarian building a learning graph of LLM papers and blog posts. "
    "You ALWAYS answer with valid JSON only, in English. No markdown, no code fences, "
    "no commentary outside the JSON."
)

# Named process configurations. "fast" < "balanced" < "deep" in thoroughness.
PRESETS = {
    "fast": {
        "llm_batch": 12, "llm_max_tokens": 2048, "llm_rel_max_tokens": 2048,
        "max_topics": 2, "llm_timeout": 180, "llm_rel_timeout": 600,
    },
    "balanced": {
        "llm_batch": 6, "llm_max_tokens": 2048, "llm_rel_max_tokens": 3072,
        "max_topics": 3, "llm_timeout": 300, "llm_rel_timeout": 900,
    },
    "deep": {
        "llm_batch": 4, "llm_max_tokens": 3072, "llm_rel_max_tokens": 4096,
        "max_topics": 4, "llm_timeout": 420, "llm_rel_timeout": 1200,
    },
}

DEFAULTS = {
    "vault": None, "sources_dir": "Fuentes", "topics_dir": "Temas",
    "topics": None, "max_topics": 3,
    "llm_url": "http://127.0.0.1:8080/v1/chat/completions",
    "llm_model": "local-llm", "llm_timeout": 300, "llm_rel_timeout": 900,
    "llm_batch": 6, "llm_max_tokens": 2048, "llm_rel_max_tokens": 3072,
    "skills_dir": None, "preset": "balanced",
}


def load_config(path: str | None) -> dict:
    """Load config.json (defaults to config.json next to the script if present)."""
    p = Path(path).expanduser() if path else (SCRIPT_DIR / "config.json")
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"⚠ Could not read config {p}: {exc}", file=sys.stderr)
        return {}
    flat = {}
    flat.update({k: v for k, v in data.items() if k in DEFAULTS})
    for key, value in (data.get("llm") or {}).items():
        if f"llm_{key}" in DEFAULTS:
            flat[f"llm_{key}"] = value
    return flat


def load_skills(path: str | None) -> str:
    """Load Markdown skill files and append them to the model's system prompt."""
    directory = Path(path).expanduser() if path else (SCRIPT_DIR / "skills")
    if not directory.is_dir():
        return ""
    chunks = []
    for skill in sorted(directory.glob("*.md")):
        text = skill.read_text(encoding="utf-8", errors="replace").strip()
        if text:
            chunks.append(f"--- SKILL: {skill.stem} ---\n{text}")
    return "\n\n".join(chunks)


def system_for(args) -> str:
    skills = getattr(args, "skills_text", "")
    return LLM_SYSTEM + ("\n\n" + skills if skills else "")


# ---------------------------------------------------------------------------
# Cache, fingerprints and content ingestion
# ---------------------------------------------------------------------------
CACHE_DIR = SCRIPT_DIR / ".cache"
PROMPT_VERSION = "v3"          # bump when prompts change to invalidate cache


def fingerprint(*parts) -> str:
    return hashlib.sha256(
        json.dumps(parts, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()[:16]


def cache_key(kind: str, payload: dict) -> str:
    return fingerprint(PROMPT_VERSION, kind, payload)


def cache_get(kind: str, key: str):
    if getattr(_CACHE_STATE, "disabled", False):
        return None
    path = CACHE_DIR / kind / f"{key}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def cache_put(kind: str, key: str, value) -> None:
    if getattr(_CACHE_STATE, "disabled", False):
        return
    path = CACHE_DIR / kind / f"{key}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


class _State:
    disabled = False
    forced = False


_CACHE_STATE = _State()


def clear_cache() -> int:
    if not CACHE_DIR.exists():
        return 0
    n = len(list(CACHE_DIR.rglob("*.json")))
    import shutil
    shutil.rmtree(CACHE_DIR)
    return n


def deduplicate_tabs(tabs: list[dict]) -> tuple[list[dict], dict[str, list[str]]]:
    """Group near-identical titles (same paper mirrored). Returns kept + map."""
    try:
        from difflib import SequenceMatcher
    except ImportError:
        return tabs, {}
    kept: list[dict] = []
    duplicates: dict[str, list[str]] = {}
    for tab in tabs:
        title = (tab.get("title") or "").strip()
        url = tab.get("url", "")
        match = None
        for i, other in enumerate(kept):
            ratio = SequenceMatcher(None, title.lower(), (other.get("title") or "").lower()).ratio()
            if ratio >= 0.82:
                match = i
                break
        if match is None:
            kept.append(tab)
        else:
            key = normalize_url(kept[match]["url"])
            duplicates.setdefault(key, []).append(url)
    return kept, duplicates


def fetch_content(url: str, timeout: int = 20, max_chars: int = 4000) -> str:
    """Best-effort text extraction from a web page or PDF."""
    key = cache_key("content", {"url": url})
    cached = cache_get("content", key)
    if cached and cached.get("text"):
        return cached["text"]
    text = ""
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 LLM-reading-queue"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(4_000_000)
        if raw[:4] == b"%PDF":
            tmp = Path("/tmp") / f"llmq-{url_hash(url)}.pdf"
            tmp.write_bytes(raw)
            try:
                import subprocess
                text = subprocess.run(["pdftotext", str(tmp), "-"], capture_output=True,
                                      text=True, timeout=30).stdout
            except Exception:
                text = ""
            finally:
                tmp.unlink(missing_ok=True)
        else:
            html_text = raw.decode("utf-8", "replace")
            html_text = re.sub(r"(?is)<(script|style|nav|footer|header).*?</\1>", " ", html_text)
            text = html.unescape(re.sub(r"(?s)<[^>]+>", " ", html_text))
    except Exception:
        text = ""
    text = re.sub(r"\s+", " ", text).strip()[:max_chars]
    cache_put("content", key, {"url": url, "text": text})
    return text


def confidence_of(rel: dict, fields: dict) -> float:
    raw = rel.get("conf", fields.get("relation_confidence", 0.8))
    try:
        return max(0.0, min(1.0, float(raw)))
    except (TypeError, ValueError):
        return 0.8


def read_minutes(url: str, source: str, content: str = "") -> int:
    if content and len(content.split()) > 80:
        return max(3, round(len(content.split()) / 220))
    return {"paper": 20, "code": 12, "blog": 8}.get(source, 10)


def extract_json(text: str):
    t = (text or "").strip()
    t = re.sub(r"^\s*```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```\s*$", "", t)
    candidates = [t]
    for opening, closing in (("{", "}"), ("[", "]")):
        start, end = t.find(opening), t.rfind(closing)
        if start != -1 and end > start:
            candidates.append(t[start:end + 1])
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except Exception:
            continue
        if isinstance(value, (dict, list)):
            return value
    return None


def ask_model(url: str, model: str, system: str, prompt: str,
              max_tokens: int, timeout: int, args=None) -> dict:
    key = cache_key("model", {
        "url": url, "model": model, "system": system, "prompt": prompt,
        "max_tokens": max_tokens,
    })
    cached = cache_get("model", key)
    if cached is not None:
        return cached

    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": max_tokens,
    }
    if getattr(args, "json_mode", False):
        payload["response_format"] = {"type": "json_object"}
    grammar_file = getattr(args, "grammar_file", None)
    if grammar_file and Path(grammar_file).exists():
        payload["grammar"] = Path(grammar_file).read_text(encoding="utf-8")

    request = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = json.loads(response.read().decode("utf-8", "replace"))
    if "choices" in data:
        content = data["choices"][0]["message"]["content"]
    elif "message" in data:
        content = data["message"]["content"]
    else:
        raise ValueError("Model response has neither 'choices' nor 'message'")
    parsed = extract_json(content)
    if isinstance(parsed, list):
        parsed = {"items": parsed}        # model returned a bare array
    if not isinstance(parsed, dict):
        raise ValueError(f"Model did not return JSON: {content[:200]!r}")
    cache_put("model", key, parsed)
    return parsed


def llm_describe_batch(items, topics, args) -> dict:
    taxonomy = "\n".join(
        f"- {name}: {', '.join(cfg.get('keywords', [])[:6]) or 'general'}"
        for name, cfg in topics.items())
    entries = json.dumps(
        [({"i": i, "title": t, "url": u, "content": c[:1500]} if c else
          {"i": i, "title": t, "url": u}) for i, t, u, c in items],
        ensure_ascii=False)
    prompt = (
        "Write a reading-queue entry for EACH source below.\n\n"
        f"TOPICS YOU MAY USE (exact names):\n{taxonomy}\n\n"
        f"SOURCES:\n{entries}\n\n"
        "Return JSON:\n"
        '{"results":[{"i":0,"topics":["RAG"],"level":2,'
        '"problem":"...","method":"...","takeaway":"..."}]}\n\n'
        "RULES:\n"
        "- Use only exact topic names from the list above, at most 3 per source.\n"
        "- 'level': 1 = beginner/foundational, 5 = advanced/research.\n"
        "- Write THREE separate parts in ENGLISH. Each part must be at least TWO "
        "full sentences (about 30 words). A one-line answer is WRONG.\n"
        "  'problem': what problem or question the source addresses;\n"
        "  'method': the main technique, argument, or content it presents;\n"
        "  'takeaway': what the reader gains and how it connects to LLMs.\n"
        "- No line breaks inside the strings.\n"
        "- Return every index from the input.\n"
    )
    parsed = ask_model(args.llm_url, args.llm_model, system_for(args), prompt,
                       args.llm_max_tokens, args.llm_timeout, args)
    rows = parsed.get("results") or parsed.get("items") or []
    results = {row["i"]: row for row in rows
               if isinstance(row, dict) and isinstance(row.get("i"), int)}
    for row in results.values():
        parts = [str(row.get(k, "")).strip() for k in ("problem", "method", "takeaway")]
        parts = [p for p in parts if p]
        if parts:
            row["description"] = " ".join(parts)
    return results


def llm_describe_all(tabs, topics, args, indices=None):
    """indices maps local position -> global tab index (for incremental runs)."""
    results = {}
    indices = indices or list(range(len(tabs)))
    items = [(indices[i], t.get("title") or t.get("url", ""), t.get("url", ""),
              str(t.get("content", ""))) for i, t in enumerate(tabs)]
    for start in range(0, len(items), args.llm_batch):
        chunk = items[start:start + args.llm_batch]
        print(f"  [1/2] descriptions: batch {start // args.llm_batch + 1} "
              f"({len(chunk)} sources)", file=sys.stderr)
        try:
            results.update(llm_describe_batch(chunk, topics, args))
        except Exception as exc:
            print(f"  ! description batch failed ({exc}); using keyword fallback",
                  file=sys.stderr)
    return results


def llm_relations(catalog, args):
    """catalog: [{i, t, topics}] -> {i: {'level':n,'pre':[j],'rel':[j]}}."""
    prompt = (
        "Build the RELATIONSHIP GRAPH for this catalog of reading-queue notes.\n\n"
        f"CATALOG ({len(catalog)} notes):\n{json.dumps(catalog, ensure_ascii=False)}\n\n"
        "For EVERY note index i decide:\n"
        "- 'level': 1 (foundational) to 5 (advanced research).\n"
        "- 'pre': up to 2 note indices that should be read BEFORE i, because they "
        "explain concepts i assumes. Only real dependencies, not vague similarity.\n"
        "- 'rel': up to 2 note indices on closely related material, NOT prerequisites.\n\n"
        "Return JSON:\n"
        '{"nodes":[{"i":0,"level":1,"pre":[3],"rel":[7]}, ...]}\n'
        "Include ALL indices, use only indices from the catalog, no self-references. "
        "English only.\n"
    )
    parsed = ask_model(args.llm_url, args.llm_model, system_for(args), prompt,
                       args.llm_rel_max_tokens, args.llm_rel_timeout, args)
    rows = parsed.get("nodes") or parsed.get("items") or []
    return {row["i"]: row for row in rows
            if isinstance(row, dict) and isinstance(row.get("i"), int)}


def topological_order(n: int, dependencies: dict[int, set[int]], levels: list[int]):
    """dependencies[i] = notes that must be read before i. Returns a stable order."""
    indegree = [len(dependencies.get(i, ())) for i in range(n)]
    dependents = [[] for _ in range(n)]
    for i in range(n):
        for j in dependencies.get(i, ()):
            if 0 <= j < n:
                dependents[j].append(i)
    heap = [(levels[i], i) for i in range(n) if indegree[i] == 0]
    heapq.heapify(heap)
    order = []
    while heap:
        _, i = heapq.heappop(heap)
        order.append(i)
        for k in dependents[i]:
            indegree[k] -= 1
            if indegree[k] == 0:
                heapq.heappush(heap, (levels[k], k))
    if len(order) < n:                      # break cycles deterministically
        rest = sorted((i for i in range(n) if indegree[i] > 0),
                      key=lambda i: (levels[i], i))
        order.extend(rest)
    return order


# ---------------------------------------------------------------------------
# Main import
# ---------------------------------------------------------------------------
def import_tabs(args) -> int:
    input_path = Path(args.input).expanduser()
    if not input_path.exists():
        print(f"✗ File not found: {input_path}", file=sys.stderr)
        return 1

    vault = Path(args.vault).expanduser()
    sources = vault / args.sources_dir
    topics_dir = vault / args.topics_dir
    sources.mkdir(parents=True, exist_ok=True)
    topics_dir.mkdir(parents=True, exist_ok=True)

    topics = load_topics(args.topics)
    if args.relations_only:
        return build_relations_only(args, sources, topics, vault)
    if args.descriptions_only:
        return build_descriptions_only(args, sources, topics, vault)

    tabs = read_tabs(input_path)
    duplicate_map: dict[str, list[str]] = {}
    if getattr(args, "dedupe", False):
        tabs, duplicate_map = deduplicate_tabs(tabs)
    n = len(tabs)

    existing: dict[str, Path] = {}
    for note in sources.glob("*.md"):
        text = note.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"(?m)^url:[ \t]*\"?([^\"\n]+)\"?", text[:1500])
        if m:
            existing.setdefault(normalize_url(m.group(1)), note)

    # deterministic note identity, needed before the relationship pass
    titles = [(t.get("title") or t.get("url", "")).strip() for t in tabs]
    filenames = [f"{slugify(title)}-{url_hash(t.get('url',''))}.md"
                 for title, t in zip(titles, tabs)]
    fps = [fingerprint(normalize_url(t.get("url", "")), titles[i], args.preset,
                       getattr(args, "skills_text", "")) for i, t in enumerate(tabs)]
    rel_fp = fingerprint("relations", *sorted(fps))
    pending = []
    for i, tab in enumerate(tabs):
        note = existing.get(normalize_url(tab.get("url", "")))
        old = ""
        if note:
            fields, _ = split_frontmatter(
                note.read_text(encoding="utf-8", errors="replace"))
            old = str(fields.get("ai_fingerprint", ""))
        if _CACHE_STATE.forced or not note or old != fps[i]:
            pending.append(i)

    descriptions, relations, order = {}, {}, list(range(n))
    if args.llm:
        print(f"  ↻ incremental: {len(pending)}/{n} sources need the model",
              file=sys.stderr)
        if getattr(args, "fetch_content", False):
            for i in pending:
                print(f"  ↓ fetching content: {tabs[i].get('url', '')[:70]}",
                      file=sys.stderr)
                tabs[i]["content"] = fetch_content(tabs[i].get("url", ""), args.llm_timeout)
        keep = [tabs[i] for i in pending]
        if keep:
            descriptions = llm_describe_all(keep, topics, args, pending)
        if not args.no_relations:
            need_relations = _CACHE_STATE.forced or any(
                str(split_frontmatter(
                    p.read_text(encoding="utf-8", errors="replace"))[0]
                    .get("relation_fingerprint", "")) != rel_fp
                for p in existing.values()
            ) or len(existing) < n
            if need_relations:
                print("  [2/2] relationships", file=sys.stderr)
                catalog = []
                for i, title in enumerate(titles):
                    tp = descriptions.get(i, {}).get("topics")
                    if not tp:
                        note = existing.get(normalize_url(tabs[i].get("url", "")))
                        if note:
                            fields, _ = split_frontmatter(
                                note.read_text(encoding="utf-8", errors="replace"))
                            tp = fields.get("topics", [])
                    catalog.append({"i": i, "t": " ".join(title.split()[:9]),
                                    "topics": tp or []})
                try:
                    relations = llm_relations(catalog, args)
                except Exception as exc:
                    print(f"  ! relationship pass failed ({exc}); using topic overlap",
                          file=sys.stderr)
                order = build_order(tabs, descriptions, relations, topics, n)
            else:
                print("  ↻ relationships unchanged (cached)", file=sys.stderr)

    created = updated = 0
    used_topics: set[str] = set()
    note_names: dict[int, str] = {}

    for i, tab in enumerate(tabs):
        url = tab.get("url", "").strip()
        if not url:
            continue
        title = titles[i]
        row = descriptions.get(i, {})
        detected = [str(t).strip() for t in row.get("topics", [])]
        detected = [t for t in detected if t in topics][:args.max_topics]
        if not detected:
            detected = classify(title, url, topics, args.max_topics)
        used_topics.update(detected)

        rel = relations.get(i, {})
        try:
            level = max(1, min(5, int(rel.get("level", row.get("level", 3)))))
        except (TypeError, ValueError):
            level = 3
        description = str(row.get("description", "")).strip()
        if description and len(description.split()) < 40:   # too short: discard
            description = ""

        target = existing.get(normalize_url(url)) or (sources / filenames[i])
        fields, _ = split_frontmatter(
            target.read_text(encoding="utf-8", errors="replace")
        ) if target.exists() else ({}, "")

        pre = valid_indices(rel.get("pre"), n, i, 2)
        related = valid_indices(rel.get("rel"), n, i, 2)

        new_fields = {
            "title": title,
            "url": url,
            "domain": urlparse(url if re.match(r"^https?://", url)
                               else "https://" + url).netloc,
            "source": infer_source(url),
            "description": description,
            "level": level,
            "status": fields.get("status", "queued"),
            "priority": fields.get("priority", "medium"),
            "topics": detected,
            "tags": ["llm"] + [topics.get(t, {}).get("tag", slugify(t)) for t in detected],
            "prerequisites": [filenames[j] for j in pre],
            "related": [filenames[j] for j in related],
            "created": fields.get("created", today()),
            "updated": stamp(),
            "user_notes": fields.get("user_notes", ""),
            "ai_fingerprint": fps[i],
            "relation_fingerprint": rel_fp,
            "read_minutes": read_minutes(url, infer_source(url),
                                         str(tabs[i].get("content", ""))),
            "relation_confidence": confidence_of(rel, fields),
            "duplicates": duplicate_map.get(normalize_url(url),
                                            fields.get("duplicates", [])),
        }

        def link(j: int) -> str:
            return f"- [[{args.sources_dir}/{Path(filenames[j]).stem}|{titles[j]}]]"

        blocks = []
        if pre:
            blocks.append("## Prerequisites\n\n" + "\n".join(link(j) for j in pre))
        if related:
            blocks.append("## Related\n\n" + "\n".join(link(j) for j in related))

        body = (
            f"# {title}\n\n"
            + (f"> [!abstract] Description\n> {description}\n\n" if description else "")
            + f"**Topics:** "
            + " · ".join(f"[[{args.topics_dir}/{t}]]" for t in detected) + "\n"
            + f"**Level:** {level} · **Status:** {new_fields['status']} · "
              f"**Priority:** {new_fields['priority']}\n\n"
            + ("\n\n".join(blocks) + "\n\n" if blocks else "")
            + "## Notes\n\n"
            + (new_fields["user_notes"] or "_(add your own notes here)_")
            + "\n"
        )

        if not getattr(args, "no_ux", False):
            body = add_status_buttons(body)

        was_new = not target.exists()
        if not args.dry_run:
            target.write_text(render_note(new_fields, body), encoding="utf-8")
            note_names[i] = Path(filenames[i]).stem
        created += was_new
        updated += not was_new

    if not args.dry_run:
        rel_sources = sources.relative_to(vault).as_posix()
        # Load the graph state from notes so incremental runs keep levels/edges.
        levels, deps, status_map = [], {i: set() for i in range(n)}, {}
        name_to_index = {fn: j for j, fn in enumerate(filenames)}
        for i, tab in enumerate(tabs):
            note = existing.get(normalize_url(tab.get("url", ""))) or (sources / filenames[i])
            fields, _ = split_frontmatter(
                note.read_text(encoding="utf-8", errors="replace")) if note.exists() else ({}, "")
            try:
                levels.append(max(1, min(5, int(fields.get("level", 3)))))
            except (TypeError, ValueError):
                levels.append(3)
            status_map[i] = str(fields.get("status", "queued"))
            for filename in fields.get("prerequisites", []) or []:
                j = name_to_index.get(str(filename))
                if j is not None:
                    deps[i].add(j)
        if relations:
            levels = levels_of(relations, descriptions, n)
            deps = dependencies_of(relations, n)
        order = topological_order(n, deps, levels)

        write_topic_notes(topics_dir, topics, used_topics, rel_sources)
        write_moc(vault, args.topics_dir, rel_sources, bool(relations) or any(deps.values()))
        write_dashboard(vault, rel_sources)
        write_learning_path(vault, order, titles, filenames, levels, rel_sources, deps)

        if not getattr(args, "no_ux", False):
            write_foundational(vault, titles, filenames, levels, deps, rel_sources)
            write_paths(vault, titles, filenames, levels, deps, rel_sources)
            write_canvas(vault, order, titles, filenames, levels, deps, rel_sources)
            write_bibtex(vault, titles, [t.get("url", "") for t in tabs])
            write_kanban(vault, rel_sources, titles, filenames, status_map)
            write_daily_snippet(vault, rel_sources)
            write_static_status(vault, rel_sources)
            write_graph_overview(vault, rel_sources)
            if getattr(args, "favicons", False):
                icons = download_favicons(vault, [t.get("url", "") for t in tabs], filenames)
                for filename, icon in icons.items():
                    note = sources / filename
                    if note.exists():
                        fields, body = split_frontmatter(
                            note.read_text(encoding="utf-8", errors="replace"))
                        fields["icon"] = icon
                        note.write_text(render_note(fields, body), encoding="utf-8")

    print(f"✓ {created} new notes · {updated} updated")
    if descriptions:
        print(f"  descriptions from local model: {len(descriptions)}/{n}")
    if relations:
        print(f"  relationship edges: {sum(len(valid_indices(r.get('pre'), n, i, 2)) + len(valid_indices(r.get('rel'), n, i, 2)) for i, r in relations.items())}")
    print(f"  vault: {vault}")
    return 0


def valid_indices(values, n: int, self_index: int, limit: int) -> list[int]:
    if not isinstance(values, list):
        return []
    out = []
    for v in values:
        try:
            j = int(v)
        except (TypeError, ValueError):
            continue
        if 0 <= j < n and j != self_index and j not in out:
            out.append(j)
        if len(out) >= limit:
            break
    return out


def dependencies_of(relations: dict, n: int) -> dict[int, set[int]]:
    deps = {i: set() for i in range(n)}
    for i, row in relations.items():
        deps[i].update(valid_indices(row.get("pre"), n, i, 2))
    return deps


def levels_of(relations: dict, descriptions: dict, n: int) -> list[int]:
    levels = []
    for i in range(n):
        raw = relations.get(i, {}).get("level", descriptions.get(i, {}).get("level", 3))
        try:
            levels.append(max(1, min(5, int(raw))))
        except (TypeError, ValueError):
            levels.append(3)
    return levels


def build_order(tabs, descriptions, relations, topics, n) -> list[int]:
    if relations:
        return topological_order(n, dependencies_of(relations, n),
                                 levels_of(relations, descriptions, n))
    # fallback: group by shared topics, then by level
    deps = {i: set() for i in range(n)}
    return topological_order(n, deps, levels_of(relations, descriptions, n))


def build_descriptions_only(args, sources: Path, topics: dict, vault: Path) -> int:
    """Regenerate English long descriptions for notes already in the vault."""
    note_paths, tabs = [], []
    for note in sorted(sources.glob("*.md")):
        fields, _ = split_frontmatter(
            note.read_text(encoding="utf-8", errors="replace"))
        if not fields.get("url"):
            continue
        note_paths.append(note)
        tabs.append({"title": str(fields.get("title") or note.stem),
                     "url": fields["url"]})
    if not tabs:
        print("✗ No notes with a URL found in the vault", file=sys.stderr)
        return 1

    results = llm_describe_all(tabs, topics, args)
    kept = 0
    for i, note in enumerate(note_paths):
        row = results.get(i, {})
        description = str(row.get("description", "")).strip()
        if len(description.split()) < 30:
            continue
        fields, body = split_frontmatter(
            note.read_text(encoding="utf-8", errors="replace"))
        detected = [str(t).strip() for t in row.get("topics", [])]
        detected = [t for t in detected if t in topics][:args.max_topics]
        if detected:
            fields["topics"] = detected
            fields["tags"] = ["llm"] + [topics[t]["tag"] for t in detected]
        try:
            fields["level"] = max(1, min(5, int(row.get("level", fields.get("level", 3)))))
        except (TypeError, ValueError):
            pass
        fields["description"] = description
        fields["updated"] = stamp()

        callout = f"> [!abstract] Description\n> {description}\n\n"
        if re.search(r"> \[!abstract\] Description\n> .*?\n\n", body, flags=re.S):
            body = re.sub(r"> \[!abstract\] Description\n> .*?\n\n",
                          lambda _m: callout, body, count=1, flags=re.S)
        else:
            body = re.sub(r"(# [^\n]+\n\n)", lambda m: m.group(1) + callout,
                          body, count=1)
        note.write_text(render_note(fields, body), encoding="utf-8")
        kept += 1
    print(f"✓ long English descriptions written for {kept}/{len(tabs)} notes")
    return 0


def build_relations_only(args, sources: Path, topics: dict, vault: Path) -> int:
    """Rebuild only the note-to-note graph from notes already in the vault."""
    note_paths, titles, filenames, descriptions = [], [], [], {}
    for note in sorted(sources.glob("*.md")):
        fields, _ = split_frontmatter(
            note.read_text(encoding="utf-8", errors="replace"))
        url = fields.get("url", "")
        if not url:
            continue
        i = len(note_paths)
        title = str(fields.get("title") or note.stem)
        note_paths.append(note)
        titles.append(title)
        filenames.append(note.name)
        descriptions[i] = {
            "topics": fields.get("topics", []),
            "description": fields.get("description", ""),
            "level": fields.get("level", 3),
        }
    n = len(note_paths)
    if not n:
        print("✗ No notes with a URL found in the vault", file=sys.stderr)
        return 1

    catalog = [{"i": i, "t": " ".join(titles[i].split()[:9]),
                "topics": descriptions[i].get("topics", [])}
               for i in range(n)]
    print(f"  [2/2] relationships for {n} notes "
          f"(timeout {args.llm_rel_timeout}s)", file=sys.stderr)
    try:
        relations = llm_relations(catalog, args)
    except Exception as exc:
        print(f"✗ relationship pass failed: {exc}", file=sys.stderr)
        return 1
    if not relations:
        print("✗ the model returned no relations", file=sys.stderr)
        return 1

    edge_count = 0
    for i, note in enumerate(note_paths):
        fields, body = split_frontmatter(
            note.read_text(encoding="utf-8", errors="replace"))
        rel = relations.get(i, {})
        pre = valid_indices(rel.get("pre"), n, i, 2)
        related = valid_indices(rel.get("rel"), n, i, 2)
        fields["prerequisites"] = [filenames[j] for j in pre]
        fields["related"] = [filenames[j] for j in related]
        try:
            fields["level"] = max(1, min(5, int(rel.get("level", fields.get("level", 3)))))
        except (TypeError, ValueError):
            pass
        fields["updated"] = stamp()

        body = re.sub(r"\n## Prerequisites\n\n.*?(?=\n## |\Z)", "\n", body, flags=re.S)
        body = re.sub(r"\n## Related\n\n.*?(?=\n## |\Z)", "\n", body, flags=re.S)

        def link(j: int) -> str:
            return f"- [[{args.sources_dir}/{Path(filenames[j]).stem}|{titles[j]}]]"

        blocks = []
        if pre:
            blocks.append("## Prerequisites\n\n" + "\n".join(link(j) for j in pre))
        if related:
            blocks.append("## Related\n\n" + "\n".join(link(j) for j in related))
        if blocks:
            insertion = "\n" + "\n\n".join(blocks) + "\n\n"
            if "\n## Notes\n" in body:
                body = body.replace("\n## Notes\n", insertion + "## Notes\n", 1)
            else:
                body = body.rstrip() + "\n" + insertion

        note.write_text(render_note(fields, body), encoding="utf-8")
        edge_count += len(pre) + len(related)

    deps = dependencies_of(relations, n)
    levels = levels_of(relations, descriptions, n)
    order = topological_order(n, deps, levels)
    write_learning_path(vault, order, titles, filenames, levels,
                        sources.relative_to(vault).as_posix(), deps)
    print(f"✓ {edge_count} relationship edges written across {n} notes")
    return 0


# ---------------------------------------------------------------------------
# Vault pages (all English)
# ---------------------------------------------------------------------------
def write_topic_notes(topics_dir: Path, topics: dict, used: set[str], rel_sources: str) -> None:
    for name, cfg in topics.items():
        tag = cfg.get("tag", slugify(name))
        content = (
            f'---\ntopic: "{name}"\ntag: "{tag}"\n---\n\n'
            f"# {name}\n\n"
            f"A topic node in the LLM reading graph. Notes link here automatically "
            f"when imported.\n\n"
            f"```dataview\n"
            f'LIST WITHOUT ID file.link + " — " + title\n'
            f'FROM "{rel_sources}"\n'
            f'WHERE contains(tags, "{tag}")\n'
            f"SORT file.name ASC\n"
            f"```\n"
        )
        (topics_dir / f"{name}.md").write_text(content, encoding="utf-8")
    generated = set(topics)
    for note in topics_dir.glob("*.md"):
        if note.stem not in generated:
            text = note.read_text(encoding="utf-8", errors="replace")
            if text.startswith("---\ntopic:"):
                note.unlink()


def write_moc(vault: Path, topics_dir: str, rel_sources: str, has_relations: bool) -> None:
    lines = ["---", "moc: true", "---", "", "# MOC — LLMs", "",
             "Map of contents. Open the Graph view to see the knowledge graph.", "",
             "## Start here", "", "- [[00-Dashboard]]",
             "- [[00-Learning Path]]" if has_relations else "- [[00-Dashboard]]",
             "", "## Topics", ""]
    lines += [f"- [[{topics_dir}/{name}|{name}]]" for name in
              sorted(p.stem for p in (vault / topics_dir).glob("*.md"))]
    lines += ["", "## All sources", "", "```dataview",
              "TABLE WITHOUT ID file.link AS Note, source AS Type, "
              "status AS Status, level AS Level",
              f'FROM "{rel_sources}"', "SORT file.name ASC", "```", ""]
    (vault / "MOC-LLMs.md").write_text("\n".join(lines), encoding="utf-8")


def write_dashboard(vault: Path, rel_sources: str) -> None:
    status_expr = '"Archived"'
    for status in reversed(STATUSES[:-1]):
        status_expr = (f'choice(status = "{status}", "{STATUS_LABEL[status]}", '
                       f"{status_expr})")
    priority_sort = 'choice(priority = "high", 0, choice(priority = "medium", 1, 2))'
    sections = []
    for status in STATUSES:
        sections += [
            f"## {STATUS_LABEL[status]}", "", "```dataview",
            "TABLE WITHOUT ID",
            f"  {status_expr} AS Status,",
            "  title AS Title,",
            '  choice(priority = "high", "High", choice(priority = "medium", "Medium", "Low")) AS Priority,',
            "  level AS Level,",
            '  join(topics, ", ") AS Topics,',
            "  file.link AS Note",
            f'FROM "{rel_sources}"',
            f'WHERE status = "{status}"',
            f"SORT {priority_sort} ASC, level ASC, file.name ASC",
            "```", "",
        ]
    content = "\n".join([
        "---", "dashboard: true", "---", "",
        "# Dashboard — sortME", "",
        "Change the `status` property of any note in Obsidian's **Properties** "
        "panel. This dashboard updates automatically.", "",
        "## Overview", "", "```dataview",
        "TABLE WITHOUT ID status AS Status, length(rows) AS Count",
        f'FROM "{rel_sources}"', "GROUP BY status", "SORT status ASC", "```", "",
        "## Next in the path", "", "```dataview",
        "LIST WITHOUT ID file.link",
        f'FROM "{rel_sources}"', 'WHERE status = "queued"',
        "SORT level ASC, file.name ASC", "LIMIT 10", "```", "",
    ] + sections + [
        "## How to use", "",
        "1. Export tabs with the browser extension.",
        "2. `python3 tabs_to_obsidian.py import tabs.json --vault <vault> --llm`",
        "3. Open [[00-Learning Path]] and follow the prerequisite chain.",
        "4. Drag notes between statuses in the Properties panel.", "",
    ])
    (vault / "00-Dashboard.md").write_text(content, encoding="utf-8")


def write_learning_path(vault: Path, order: list[int], titles: list[str],
                        filenames: list[str], levels: list[int], rel_sources: str,
                        deps: dict[int, set[int]]) -> None:
    lines = ["---", "learning_path: true", "---", "",
             "# Learning Path — LLMs", "",
             "Suggested reading order inferred by the local model from prerequisite "
             "links between notes. Each note also links to its prerequisites and "
             "related notes in the body, so Obsidian's Graph view shows the full "
             "relationship graph.", ""]

    # Mermaid subgraph of the first dependency edges (kept small and readable)
    mermaid = ["```mermaid", "flowchart LR"]
    count = 0
    for i in order[:24]:
        for j in sorted(deps.get(i, ())):
            if j not in order[:24]:
                continue
            a = re.sub(r'[^A-Za-z0-9 ]', '', titles[j][:26])
            b = re.sub(r'[^A-Za-z0-9 ]', '', titles[i][:26])
            mermaid.append(f'  N{j}["{a}"] --> N{i}["{b}"]')
            count += 1
            if count >= 18:
                break
        if count >= 18:
            break
    if count:
        lines += mermaid + ["```", ""]

    current_level = None
    position = 0
    for i in order:
        lvl = levels[i]
        if lvl != current_level:
            current_level = lvl
            if lines and lines[-1] != "":
                lines.append("")
            lines += [f"## Level {lvl}", ""]
        position += 1
        stem = Path(filenames[i]).stem
        lines.append(f"{position}. [[{rel_sources}/{stem}|{titles[i]}]]")
    lines.append("")
    (vault / "00-Learning Path.md").write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Status / CLI
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Graph analytics and Obsidian UX artifacts
# ---------------------------------------------------------------------------
def indegrees(n: int, deps: dict[int, set[int]]) -> list[int]:
    counts = [0] * n
    for i in range(n):
        for j in deps.get(i, ()):
            if 0 <= j < n:
                counts[j] += 1
    return counts


def write_foundational(vault: Path, titles: list[str], filenames: list[str],
                       levels: list[int], deps: dict[int, set[int]],
                       rel_sources: str) -> None:
    counts = indegrees(len(titles), deps)
    top = sorted(range(len(titles)), key=lambda i: (-counts[i], levels[i]))[:10]
    lines = ["---", "foundational: true", "---", "", "# Foundational Notes", "",
             "Ranked by how many other notes depend on them (in-degree of the "
             "prerequisite graph). Start here if you are short on time.", "",
             "| Note | Unlocks | Level |", "|---|---:|---:|"]
    for i in top:
        stem = Path(filenames[i]).stem
        lines.append(f"| [[{rel_sources}/{stem}]] | {counts[i]} | {levels[i]} |")
    lines.append("")
    (vault / "00-Foundational Notes.md").write_text("\n".join(lines), encoding="utf-8")


def write_paths(vault: Path, titles: list[str], filenames: list[str],
                levels: list[int], deps: dict[int, set[int]],
                rel_sources: str, limit: int = 5) -> None:
    folder = vault / "Paths"
    folder.mkdir(parents=True, exist_ok=True)
    counts = indegrees(len(titles), deps)
    targets = sorted(range(len(titles)), key=lambda i: (-counts[i], levels[i]))[:limit]
    for target in targets:
        seen, stack = set(), [target]
        while stack:
            cur = stack.pop()
            for pre in deps.get(cur, ()):
                if 0 <= pre < len(titles) and pre not in seen:
                    seen.add(pre)
                    stack.append(pre)
        ordered = sorted(seen, key=lambda i: (levels[i], i))
        lines = ["---", "path_to: \"" + titles[target] + "\"", "---", "",
                 f"# Path to: {titles[target]}", "",
                 "Prerequisite chain inferred from the relationship graph. "
                 "Read from top to bottom.", ""]
        for position, i in enumerate(ordered, 1):
            stem = Path(filenames[i]).stem
            lines.append(f"{position}. [[{rel_sources}/{stem}|{titles[i]}]]")
        if not ordered:
            lines.append("_No prerequisites detected — this note can be read directly._")
        lines.append("")
        (folder / f"To {slugify(titles[target], 40)}.md").write_text(
            "\n".join(lines), encoding="utf-8")


def write_canvas(vault: Path, order: list[int], titles: list[str],
                 filenames: list[str], levels: list[int],
                 deps: dict[int, set[int]], rel_sources: str) -> None:
    nodes, edges = [], []
    for k, i in enumerate(order):
        nodes.append({
            "id": f"n{i}", "type": "file",
            "file": f"{rel_sources}/{filenames[i]}",
            "x": levels[i] * 420, "y": k * 120, "width": 340, "height": 100,
        })
    for i in range(len(titles)):
        for j in deps.get(i, ()):
            if 0 <= j < len(titles):
                edges.append({"id": f"e{j}-{i}", "fromNode": f"n{j}", "toNode": f"n{i}"})
    (vault / "00-Knowledge Map.canvas").write_text(
        json.dumps({"nodes": nodes, "edges": edges}, ensure_ascii=False, indent=2),
        encoding="utf-8")


def write_bibtex(vault: Path, titles: list[str], urls: list[str]) -> None:
    entries = []
    for title, url in zip(titles, urls):
        m = re.search(r"arxiv\.org/(?:abs|pdf)/([0-9.]+)", url)
        year = ("20" + m.group(1)[:2]) if m else str(datetime.now().year)
        key = re.sub(r"[^A-Za-z0-9]", "", title.split()[0].lower()) + year
        entries.append(
            f"@misc{{{key},\n  title={{{title}}},\n  url={{{url}}},\n  year={{{year}}}\n}}")
    (vault / "references.bib").write_text("\n\n".join(entries) + "\n", encoding="utf-8")


def write_kanban(vault: Path, rel_sources: str, titles: list[str],
                 filenames: list[str], status_map: dict[int, str]) -> None:
    lines = ["---", "kanban-plugin: board", "---", ""]
    for status, label in (("queued", "To read"), ("reading", "Reading"),
                          ("read", "Read"), ("archived", "Archived")):
        lines += [f"## {label}", ""]
        for i, current in status_map.items():
            if current == status:
                stem = Path(filenames[i]).stem
                lines.append(f"- [[{rel_sources}/{stem}|{titles[i]}]]")
        lines.append("")
    lines += ["%% kanban:settings", "```", '{"kanban-plugin":"board"}', "```", "%%"]
    (vault / "00-Queue Kanban.kanban").write_text("\n".join(lines), encoding="utf-8")


def write_daily_snippet(vault: Path, rel_sources: str) -> None:
    (vault / "00-Daily Queue Snippet.md").write_text("\n".join([
        "---", "snippet: true", "---", "", "# Daily queue snippet", "",
        "Copy the block below into your daily note. It shows a small, "
        "level-ordered slice of the reading queue.", "",
        "```dataview", "LIST WITHOUT ID file.link + \" — \" + title",
        f'FROM "{rel_sources}"', 'WHERE status = "queued"',
        "SORT level ASC, file.name ASC", "LIMIT 3", "```", "",
    ]), encoding="utf-8")


def add_status_buttons(body: str) -> str:
    block = (
        "> [!tip] Quick status\n"
        "> ```dataviewjs\n"
        "> const f = dv.current().file;\n"
        "> for (const s of [\"queued\", \"reading\", \"read\", \"archived\"]) {\n"
        ">   dv.el(\"button\", \"Set \" + s, { onclick: async () => { "
        "await app.fileManager.processFrontMatter(f, fm => fm.status = s); } });\n"
        "> }\n"
        "> ```\n"
    )
    body = re.sub(r"\n?> \[!tip\] Quick status\n(?:> .*\n)*", "\n", body)
    return body.rstrip() + "\n\n" + block


def download_favicons(vault: Path, urls: list[str], filenames: list[str]) -> dict[str, str]:
    folder = vault / args_sources_dir(vault) / "icons"
    folder.mkdir(parents=True, exist_ok=True)
    result = {}
    for url, filename in zip(urls, filenames):
        try:
            domain = urlparse(url if re.match(r"^https?://", url)
                              else "https://" + url).netloc
        except Exception:
            continue
        candidates = [
            f"https://www.google.com/s2/favicons?domain={domain}&sz=64",
            f"https://{domain}/favicon.ico",
        ]
        for candidate in candidates:
            try:
                request = urllib.request.Request(candidate,
                                                 headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(request, timeout=8) as response:
                    data = response.read(200_000)
                if len(data) < 100:
                    continue
                icon_name = f"{Path(filename).stem}.ico"
                (folder / icon_name).write_bytes(data)
                result[filename] = f"{args_sources_dir(vault)}/icons/{icon_name}"
                break
            except Exception:
                continue
    return result


def args_sources_dir(vault: Path) -> str:
    """Best-effort detection of the sources folder name."""
    for name in ("Fuentes", "Sources", "Fuentes/"):
        if (vault / name.rstrip("/")).is_dir():
            return name.rstrip("/")
    return "Fuentes"


def run_doctor(args) -> int:
    print("🩺 sortME — doctor\n")
    ok = True

    def report(label: str, good: bool, detail: str = "") -> None:
        nonlocal ok
        print(f"  {'✓' if good else '✗'} {label}" + (f" — {detail}" if detail else ""))
        ok = ok and good

    report("Python 3.8+", sys.version_info >= (3, 8), sys.version.split()[0])
    topics_path = Path(args.topics).expanduser() if getattr(args, "topics", None) \
        else (SCRIPT_DIR / "topics.json")
    try:
        topics = json.loads(topics_path.read_text(encoding="utf-8"))
        report("topics.json", isinstance(topics, dict) and len(topics) > 0,
               f"{len(topics)} topics")
    except Exception as exc:
        report("topics.json", False, str(exc))

    skills = getattr(args, "skills_text", "")
    report("skills", bool(skills), f"{len(skills)} chars")

    vault = Path(args.vault).expanduser() if getattr(args, "vault", None) else None
    report("vault path", bool(vault and vault.is_dir()), str(vault or "not set"))
    if vault:
        plugins = vault / ".obsidian" / "plugins" / "dataview"
        report("Dataview plugin", plugins.is_dir(), str(plugins))

    url = getattr(args, "llm_url", "http://127.0.0.1:8080/v1/chat/completions")
    try:
        health = url.split("/v1/")[0] + "/health"
        with urllib.request.urlopen(health, timeout=3) as response:
            payload = json.loads(response.read().decode())
        report("local model", payload.get("status") == "ok", health)
    except Exception as exc:
        report("local model", False, str(exc))

    report("cache directory", CACHE_DIR.is_dir() or True, str(CACHE_DIR))
    print(f"\n{'✓ All checks passed' if ok else '✗ Some checks failed'}")
    return 0 if ok else 1


# ---------------------------------------------------------------------------
# Search / RAG over the vault
# ---------------------------------------------------------------------------
def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]{3,}", (text or "").lower())


def tfidf_rank(texts: list[str], query: str, top_k: int) -> list[tuple[int, float]]:
    docs = [_tokenize(t) for t in texts]
    q = _tokenize(query)
    if not docs or not q:
        return []
    df: dict[str, int] = {}
    for doc in docs:
        for word in set(doc):
            df[word] = df.get(word, 0) + 1
    n = len(docs)
    idf = {w: 1.0 + __import__("math").log(n / (1 + c)) for w, c in df.items()}
    scores = []
    for i, doc in enumerate(docs):
        counts = __import__("collections").Counter(doc)
        norm = max(1, len(doc))
        score = sum(counts[w] / norm * idf.get(w, 0.0) for w in q)
        scores.append((i, score))
    scores.sort(key=lambda x: -x[1])
    return scores[:top_k]


def embedding_rank(texts: list[str], query: str, args, top_k: int):
    endpoint = args.llm_url.replace("/v1/chat/completions", "/v1/embeddings")
    payload = {"model": args.llm_model, "input": [query] + texts}
    request = urllib.request.Request(
        endpoint, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=args.llm_timeout) as response:
        data = json.loads(response.read().decode("utf-8", "replace"))
    vectors = [row["embedding"] for row in sorted(data["data"], key=lambda r: r["index"])]
    if len(vectors) != len(texts) + 1:
        raise ValueError("unexpected embedding count")
    qv = vectors[0]

    def cosine(a, b):
        dot = sum(x * y for x, y in zip(a, b))
        na = sum(x * x for x in a) ** 0.5
        nb = sum(y * y for y in b) ** 0.5
        return dot / (na * nb) if na and nb else 0.0

    scores = [(i, cosine(qv, v)) for i, v in enumerate(vectors[1:])]
    scores.sort(key=lambda x: -x[1])
    return scores[:top_k]


def retrieve_notes(args, query: str, top_k: int = 5):
    vault = Path(args.vault).expanduser()
    sources = vault / getattr(args, "sources_dir", "Fuentes")
    entries = []
    for path in sorted(sources.glob("*.md")):
        fields, body = split_frontmatter(
            path.read_text(encoding="utf-8", errors="replace"))
        entries.append((path, fields, body))
    texts = []
    for _path, fields, body in entries:
        texts.append(" ".join(str(fields.get(k, "")) for k in
                              ("title", "description", "topics")) + " " + body[:1200])
    ranked = None
    if getattr(args, "embeddings", False):
        try:
            ranked = embedding_rank(texts, query, args, top_k)
        except Exception as exc:
            print(f"⚠ embeddings unavailable ({exc}); using TF-IDF", file=sys.stderr)
    if ranked is None:
        ranked = tfidf_rank(texts, query, top_k)
    result = []
    for i, score in ranked:
        if score <= 0:
            continue
        result.append((entries[i][0], entries[i][1], entries[i][2], score))
    return result


def search_notes(args) -> int:
    results = retrieve_notes(args, " ".join(args.query), args.top)
    if not results:
        print("No matching notes.")
        return 0
    for path, fields, _body, score in results:
        print(f"{score:6.3f}  {fields.get('title', path.stem)}")
        print(f"         {path}")
    return 0


def ask_notes(args) -> int:
    results = retrieve_notes(args, " ".join(args.query), 5)
    if not results:
        print("No matching notes to answer from.")
        return 1
    context = "\n\n".join(
        f"SOURCE: {fields.get('title', path.stem)}\n"
        f"DESCRIPTION: {fields.get('description', '')}\n"
        f"NOTES: {body[:800]}"
        for path, fields, body, _score in results
    )
    prompt = (
        "Answer the question using ONLY the sources below. If the answer is not "
        "present, say so. Return JSON: {\"answer\":\"...\", \"sources\":[\"title\", ...]}.\n\n"
        f"QUESTION: {' '.join(args.query)}\n\nSOURCES:\n{context}"
    )
    parsed = ask_model(args.llm_url, args.llm_model,
                       "You answer questions from a research library. JSON only, English.",
                       prompt, 1024, args.llm_timeout, args)
    print(parsed.get("answer", parsed))
    sources = parsed.get("sources") or []
    if sources:
        print("\nSources: " + ", ".join(str(s) for s in sources))
    return 0


# ---------------------------------------------------------------------------
# Input feeders
# ---------------------------------------------------------------------------
def write_tabs_file(tabs: list[dict], output: str) -> int:
    path = Path(output).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "exported_at": stamp(), "source": "feeder", "tabs": tabs
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✓ {len(tabs)} tabs written to {path}")
    return 0


def feed_arxiv(args) -> int:
    from urllib.parse import quote
    import xml.etree.ElementTree as ET
    endpoint = ("http://export.arxiv.org/api/query?search_query=all:"
                f"{quote(args.query)}&start=0&max_results={args.max_results}")
    with urllib.request.urlopen(endpoint, timeout=30) as response:
        xml = response.read()
    ns = {"a": "http://www.w3.org/2005/Atom"}
    roots = ET.fromstring(xml)
    tabs = []
    for entry in roots.findall("a:entry", ns):
        title = entry.findtext("a:title", "", namespaces=ns)
        url = entry.findtext("a:id", "", namespaces=ns)
        if title and url:
            tabs.append({"title": " ".join(title.split()), "url": url.strip()})
    return write_tabs_file(tabs, args.output)


def import_zotero(args) -> int:
    endpoint = "http://127.0.0.1:23119/api/users/0/items?format=json&limit=200"
    with urllib.request.urlopen(endpoint, timeout=20) as response:
        items = json.loads(response.read().decode("utf-8", "replace"))
    tabs = []
    for item in items:
        url = item.get("url") or item.get("DOI")
        title = item.get("title")
        if title and url:
            tabs.append({"title": title, "url": ("https://doi.org/" + url)
                         if str(url).startswith("10.") else url})
    return write_tabs_file(tabs, args.output)


def import_readwise(args) -> int:
    import os
    token = args.token or os.environ.get("READWISE_TOKEN")
    if not token:
        print("✗ provide --token or READWISE_TOKEN", file=sys.stderr)
        return 1
    tabs, page = [], 1
    while True:
        endpoint = f"https://readwise.io/api/v2/list/?category=articles&page_size=100&page={page}"
        request = urllib.request.Request(endpoint,
                                         headers={"Authorization": f"Token {token}"})
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8", "replace"))
        batch = data.get("results", [])
        for item in batch:
            if item.get("url") and item.get("title"):
                tabs.append({"title": item["title"], "url": item["url"]})
        if not data.get("next") or not batch:
            break
        page += 1
    return write_tabs_file(tabs, args.output)


def run_watch(args) -> int:
    import time as _time
    import subprocess
    folder = Path(args.watch_dir).expanduser()
    folder.mkdir(parents=True, exist_ok=True)
    done = folder / "processed"
    done.mkdir(exist_ok=True)
    print(f"👀 watching {folder} every {args.interval}s (Ctrl+C to stop)")
    try:
        while True:
            for tab_file in sorted(folder.glob("*.json")):
                cmd = [sys.executable, str(Path(__file__).resolve()), "import",
                       str(tab_file)]
                if args.config:
                    cmd += ["--config", args.config]
                if args.llm:
                    cmd += ["--llm"]
                print(f"→ importing {tab_file.name}")
                result = subprocess.run(cmd)
                if result.returncode == 0:
                    tab_file.rename(done / tab_file.name)
            _time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nwatch stopped")
    return 0


def run_eval(args) -> int:
    labels_path = Path(args.labels).expanduser()
    labels = json.loads(labels_path.read_text(encoding="utf-8"))
    vault = Path(args.vault).expanduser()
    sources = vault / getattr(args, "sources_dir", "Fuentes")
    notes = []
    for path in sources.glob("*.md"):
        fields, body = split_frontmatter(
            path.read_text(encoding="utf-8", errors="replace"))
        notes.append((fields, body))
    topic_ok = topic_total = rel_ok = rel_total = 0
    for label in labels:
        match = next((f for f, _ in notes
                      if str(label.get("title_contains", "")).lower()
                      in str(f.get("title", "")).lower()), None)
        if not match:
            print(f"✗ missing note: {label.get('title_contains')}")
            continue
        expected = set(label.get("topics", []))
        actual = set(match.get("topics", []))
        topic_total += len(expected)
        topic_ok += len(expected & actual)
        if "related_contains" in label:
            needle = str(label["related_contains"]).lower()
            rel_total += 1
            hit = any(needle in str(x).lower() for x in
                      (match.get("related", []) or []))
            rel_ok += int(hit)
    print(f"topic precision/recall overlap: {topic_ok}/{topic_total}")
    if rel_total:
        print(f"relation hits: {rel_ok}/{rel_total}")
    return 0


# ---------------------------------------------------------------------------
# Plugin-free status view and organised graph overview
# ---------------------------------------------------------------------------
def collect_vault_notes(vault: Path, sources_dir: str = "Fuentes",
                        include_excluded: bool = False):
    sources = vault / sources_dir
    rows = []
    for path in sorted(sources.glob("*.md")):
        fields, body = split_frontmatter(
            path.read_text(encoding="utf-8", errors="replace"))
        if not include_excluded and fields.get("excluded"):
            continue
        rows.append((path, fields, body))
    return rows


def write_static_status(vault: Path, sources_dir: str = "Fuentes") -> None:
    """A plain-Markdown queue that works even without Dataview."""
    rows = collect_vault_notes(vault, sources_dir, include_excluded=True)
    labels = (("queued", "To read"), ("reading", "Reading"),
              ("read", "Read"), ("archived", "Archived"))
    lines = ["---", "static_status: true", "---", "",
             "# Status — sortME", "",
             "This page is plain Markdown: it always renders, even without "
             "Dataview. To change a note's state, open it and edit the "
             "`status` property in Obsidian's **Properties** panel.", "",
             f"_Updated: {stamp()}_", "", "## Overview", "",
             "| Status | Count |", "|---|---:|"]
    for status, label in labels:
        count = sum(1 for _p, f, _b in rows if f.get("status", "queued") == status)
        lines.append(f"| {label} | {count} |")
    lines.append("")
    for status, label in labels:
        lines += [f"## {label}", "",
                  "| Note | Level | Topics | Min |", "|---|---:|---|---:|"]
        group = [(p, f) for p, f, _b in rows if f.get("status", "queued") == status]
        group.sort(key=lambda x: (int(x[1].get("level", 3) or 3), x[0].name))
        for path, fields in group:
            topics = ", ".join(str(t) for t in (fields.get("topics") or []))
            lines.append(
                f"| [[{sources_dir}/{path.stem}\\|{fields.get('title', path.stem)}]] "
                f"| {fields.get('level', '-')} | {topics} "
                f"| {fields.get('read_minutes', '-')} |")
        if not group:
            lines.append("| _(empty)_ | | | |")
        lines.append("")
    (vault / "00-Status.md").write_text("\n".join(lines), encoding="utf-8")


def write_graph_overview(vault: Path, sources_dir: str = "Fuentes") -> None:
    """Organised graph: topic clusters as Mermaid subgraphs + level pyramid."""
    rows = collect_vault_notes(vault, sources_dir)
    name_to_index = {p.stem: i for i, (p, _f, _b) in enumerate(rows)}
    levels = []
    for _p, fields, _b in rows:
        try:
            levels.append(max(1, min(5, int(fields.get("level", 3)))))
        except (TypeError, ValueError):
            levels.append(3)

    clusters: dict[str, list[int]] = {}
    for i, (_p, fields, _b) in enumerate(rows):
        topic = (fields.get("topics") or ["General"])[0]
        clusters.setdefault(str(topic), []).append(i)
    top_clusters = sorted(clusters.items(), key=lambda kv: -len(kv[1]))[:8]

    lines = ["---", "graph_overview: true", "---", "",
             "# Graph overview — organised", "",
             "A clustered view of the relationship graph. Nodes are grouped by "
             "their primary topic; arrows are prerequisites. For the interactive "
             "version open [[00-Knowledge Map]] in Canvas or the Obsidian Graph view.",
             "", "## Clusters", "", "```mermaid", "flowchart LR"]
    for ci, (topic, indices) in enumerate(top_clusters):
        safe_topic = re.sub(r"[^A-Za-z0-9 ]", "", topic)
        lines.append(f'  subgraph C{ci}["{safe_topic} ({len(indices)})"]')
        for i in indices[:6]:
            title = rows[i][1].get("title", rows[i][0].stem)
            label = re.sub(r'[^A-Za-z0-9 ]', '', str(title))[:28]
            lines.append(f'    N{i}["{label}"]')
        lines.append("  end")
    for i, (_p, fields, _b) in enumerate(rows):
        for dep in fields.get("prerequisites", []) or []:
            j = name_to_index.get(str(Path(str(dep)).stem))
            if j is not None and j in {k for _t, ids in top_clusters for k in ids[:6]} \
                    and i in {k for _t, ids in top_clusters for k in ids[:6]}:
                lines.append(f"  N{j} --> N{i}")
    lines += ["```", "", "## Level pyramid", "",
              "| Level | Notes |", "|---:|---:|"]
    for level in range(1, 6):
        lines.append(f"| {level} | {sum(1 for x in levels if x == level)} |")
    lines += ["", "## Links", "", "- [[00-Learning Path]]",
              "- [[00-Foundational Notes]]", "- [[00-Status]]",
              "- [[00-Knowledge Map]] (Canvas)", ""]
    (vault / "00-Graph Overview.md").write_text("\n".join(lines), encoding="utf-8")


JUNK_TITLE_PATTERNS = [
    r"^\s*chatgpt\s*$", r"leetcode", r"neetcode", r"daily temperatures",
    r"subarray sum", r"jkanime", r"anime", r"episodio", r"opencode console",
    r"^activity\b", r"free-claude-code", r"free tokens", r"alltime\.csv",
    r"^untitled", r"^list to do", r"^stocks to watch",
]


def is_junk_title(title: str) -> bool:
    lowered = (title or "").lower()
    return any(re.search(p, lowered) for p in JUNK_TITLE_PATTERNS)


def validate_graph(args, rows) -> tuple[dict[int, bool], set[tuple[int, int, str]]]:
    """Ask the SAME local model to reject junk sources and nonsensical edges."""
    name_to_index = {p.stem: i for i, (p, _f, _b) in enumerate(rows)}
    catalog = [{"i": i, "title": str(f.get("title", p.stem)),
                "topics": f.get("topics", [])}
               for i, (p, f, _b) in enumerate(rows)]
    edges = []
    for i, (_p, fields, _body) in enumerate(rows):
        for dep in fields.get("prerequisites", []) or []:
            j = name_to_index.get(str(Path(str(dep)).stem))
            if j is not None:
                edges.append({"from": i, "to": j, "type": "pre"})
        for dep in fields.get("related", []) or []:
            j = name_to_index.get(str(Path(str(dep)).stem))
            if j is not None:
                edges.append({"from": i, "to": j, "type": "rel"})
    prompt = (
        "You are auditing an LLM research reading graph. Remove noise.\n\n"
        f"NOTES ({len(catalog)}):\n{json.dumps(catalog, ensure_ascii=False)}\n\n"
        f"EDGES ({len(edges)}):\n{json.dumps(edges, ensure_ascii=False)}\n\n"
        "Return JSON:\n"
        '{"notes":[{"i":0,"keep":true,"reason":"..."}],'
        '"edges":[{"from":0,"to":3,"type":"pre","keep":false,"reason":"..."}]}\n\n'
        "RULES:\n"
        "- keep=false for a NOTE if it is not a genuine LLM/ML paper, blog post "
        "or technical resource. Examples to reject: generic coding-challenge "
        "pages (LeetCode/NeetCode), anime or video sites, product login/console "
        "pages, generic interview lists, PDFs with no identifiable topic, and "
        "anything unrelated to LLMs or machine learning.\n"
        "- keep=false for an EDGE if the claimed prerequisite or related "
        "relationship is not real. A random ChatGPT page is NOT a prerequisite "
        "for unrelated papers. Prefer removing weak edges.\n"
        "- Include EVERY note index and EVERY edge exactly once.\n"
        "- Be strict: a noisy graph is worse than a small clean one.\n"
    )
    parsed = ask_model(args.llm_url, args.llm_model, system_for(args), prompt,
                       args.llm_rel_max_tokens, args.llm_rel_timeout, args)
    raw_notes = list(parsed.get("notes") or [])
    raw_edges = list(parsed.get("edges") or [])
    for row in parsed.get("items") or []:
        if not isinstance(row, dict):
            continue
        if "from" in row and "to" in row:
            raw_edges.append(row)
        elif isinstance(row.get("i"), int):
            raw_notes.append(row)

    note_keep = {}
    for row in raw_notes:
        if isinstance(row, dict) and isinstance(row.get("i"), int):
            note_keep[row["i"]] = bool(row.get("keep", True))
    drop_edges = set()
    for row in raw_edges:
        if isinstance(row, dict) and not row.get("keep", True):
            try:
                drop_edges.add((int(row["from"]), int(row["to"]), str(row.get("type", ""))))
            except (KeyError, TypeError, ValueError):
                pass
    return note_keep, drop_edges


def validate_edges_with_model(args, rows, active: set[int]) -> set[tuple[int, int, str]]:
    """Second model pass: audit only the prerequisite/related edges."""
    name_to_index = {p.stem: i for i, (p, _f, _b) in enumerate(rows)}
    edges = []
    for i, (_p, fields, _body) in enumerate(rows):
        if i not in active:
            continue
        for dep in fields.get("prerequisites", []) or []:
            j = name_to_index.get(str(Path(str(dep)).stem))
            if j is not None and j in active:
                edges.append({"from": i, "to": j, "type": "pre"})
        for dep in fields.get("related", []) or []:
            j = name_to_index.get(str(Path(str(dep)).stem))
            if j is not None and j in active:
                edges.append({"from": i, "to": j, "type": "rel"})
    if not edges:
        return set()

    catalog = {i: str(f.get("title", p.stem))[:90]
               for i, (p, f, _b) in enumerate(rows) if i in active}
    pairs = []
    for edge in edges:
        pairs.append({"from": edge["from"], "to": edge["to"], "type": edge["type"],
                      "from_title": catalog.get(edge["from"], ""),
                      "to_title": catalog.get(edge["to"], "")})
    prompt = (
        "Audit these edges of an LLM reading graph. Return a JSON array only.\n\n"
        f"EDGES:\n{json.dumps(pairs, ensure_ascii=False)}\n\n"
        "Each item: {\"from\":F,\"to\":T,\"type\":\"pre|rel\",\"keep\":true|false,\"reason\":\"...\"}\n"
        "keep=false when the relationship is not real: a prerequisite must be a "
        "concept the other note actually builds on; related must be genuinely "
        "close work. Remove weak or random links. Include EVERY edge once.\n"
    )
    parsed = ask_model(args.llm_url, args.llm_model, system_for(args), prompt,
                       args.llm_rel_max_tokens, args.llm_rel_timeout, args)
    rows_out = parsed.get("edges") or parsed.get("items") or []
    drop = set()
    for row in rows_out:
        if isinstance(row, dict) and not row.get("keep", True):
            try:
                drop.add((int(row["from"]), int(row["to"]), str(row.get("type", ""))))
            except (KeyError, TypeError, ValueError):
                pass
    return drop


def validate_cmd(args) -> int:
    vault = Path(args.vault).expanduser()
    rows = collect_vault_notes(vault, getattr(args, "sources_dir", "Fuentes"),
                               include_excluded=True)
    if not rows:
        print("✗ no notes found", file=sys.stderr)
        return 1
    print(f"🔍 validating {len(rows)} notes with the local model...", file=sys.stderr)
    note_keep, drop_edges = validate_graph(args, rows)
    # deterministic rules always apply, even if the model is lenient
    for i, (_p, fields, _b) in enumerate(rows):
        if is_junk_title(str(fields.get("title", ""))):
            note_keep[i] = False
        elif is_junk_title(_p.stem):
            note_keep[i] = False

    active = {i for i in range(len(rows)) if note_keep.get(i, True)}
    drop_edges |= validate_edges_with_model(args, rows, active)

    excluded = [i for i, keep in note_keep.items() if not keep]
    removed = len(drop_edges)
    print(f"  notes to archive: {len(excluded)} · edges to drop: {removed}")
    if getattr(args, "dry_run", False):
        for i in excluded:
            print(f"    - {rows[i][1].get('title', rows[i][0].stem)}")
        return 0

    name_to_index = {p.stem: i for i, (p, _f, _b) in enumerate(rows)}
    for i, (path, fields, body) in enumerate(rows):
        drop_pre = {j for (a, j, t) in drop_edges if a == i and t == "pre"}
        drop_rel = {j for (a, j, t) in drop_edges if a == i and t == "rel"}
        excluded_set = set(excluded)
        kept_pre = [x for x in (fields.get("prerequisites") or [])
                    if name_to_index.get(str(Path(str(x)).stem)) not in drop_pre
                    and name_to_index.get(str(Path(str(x)).stem)) not in excluded_set]
        kept_rel = [x for x in (fields.get("related") or [])
                    if name_to_index.get(str(Path(str(x)).stem)) not in drop_rel
                    and name_to_index.get(str(Path(str(x)).stem)) not in excluded_set]
        fields["prerequisites"] = kept_pre
        fields["related"] = kept_rel
        if i in note_keep and not note_keep[i]:
            fields["excluded"] = True
            fields["status"] = "archived"
            fields["excluded_reason"] = "filtered by local model validation"
        fields["updated"] = stamp()

        body = re.sub(r"\n## Prerequisites\n\n.*?(?=\n## |\Z)", "\n", body, flags=re.S)
        body = re.sub(r"\n## Related\n\n.*?(?=\n## |\Z)", "\n", body, flags=re.S)
        blocks = []
        if kept_pre:
            lines = ["## Prerequisites", ""]
            for dep in kept_pre:
                j = name_to_index.get(str(Path(str(dep)).stem))
                label = rows[j][1].get("title", dep) if j is not None else dep
                lines.append(f"- [[{getattr(args, 'sources_dir', 'Fuentes')}/{Path(str(dep)).stem}|{label}]]")
            blocks.append("\n".join(lines))
        if kept_rel:
            lines = ["## Related", ""]
            for dep in kept_rel:
                j = name_to_index.get(str(Path(str(dep)).stem))
                label = rows[j][1].get("title", dep) if j is not None else dep
                lines.append(f"- [[{getattr(args, 'sources_dir', 'Fuentes')}/{Path(str(dep)).stem}|{label}]]")
            blocks.append("\n".join(lines))
        if blocks:
            insertion = "\n" + "\n\n".join(blocks) + "\n\n"
            if "\n## Notes\n" in body:
                body = body.replace("\n## Notes\n", insertion + "## Notes\n", 1)
            else:
                body = body.rstrip() + "\n" + insertion
        path.write_text(render_note(fields, body), encoding="utf-8")

    refresh_ux(type("A", (), {
        "vault": str(vault),
        "sources_dir": getattr(args, "sources_dir", "Fuentes"),
    })())
    print(f"✓ validation applied: {len(excluded)} notes archived, {removed} edges removed")
    return 0


def refresh_ux(args) -> int:
    """Regenerate all derived Obsidian files from existing notes, no model calls."""
    vault = Path(args.vault).expanduser()
    sources = vault / getattr(args, "sources_dir", "Fuentes")
    if not vault.is_dir():
        print(f"✗ vault not found: {vault}", file=sys.stderr)
        return 1
    rows = collect_vault_notes(vault, getattr(args, "sources_dir", "Fuentes"))
    if not rows:
        print("✗ no notes found", file=sys.stderr)
        return 1

    # add the status hint + buttons to every note body, idempotently
    for path, fields, body in rows:
        body = add_status_buttons(body)
        hint = "> [!tip] Change state\n> Edit the `status` property in the Properties panel (queued / reading / read / archived)."
        body = re.sub(r"\n?> \[!tip\] Change state\n> .*\n", "\n", body)
        body = body.rstrip() + "\n\n" + hint + "\n"
        path.write_text(render_note(fields, body), encoding="utf-8")

    write_static_status(vault, getattr(args, "sources_dir", "Fuentes"))
    write_graph_overview(vault, getattr(args, "sources_dir", "Fuentes"))

    titles = [str(f.get("title", p.stem)) for p, f, _b in rows]
    filenames = [p.name for p, _f, _b in rows]
    urls = [str(f.get("url", "")) for p, f, _b in rows]
    levels, deps, status_map = [], {i: set() for i in range(len(rows))}, {}
    name_to_index = {fn: i for i, fn in enumerate(filenames)}
    for i, (_p, fields, _b) in enumerate(rows):
        try:
            levels.append(max(1, min(5, int(fields.get("level", 3)))))
        except (TypeError, ValueError):
            levels.append(3)
        status_map[i] = str(fields.get("status", "queued"))
        for dep in fields.get("prerequisites", []) or []:
            j = name_to_index.get(str(Path(str(dep)).stem))
            if j is not None:
                deps[i].add(j)
    order = topological_order(len(rows), deps, levels)
    rel_sources = getattr(args, "sources_dir", "Fuentes")
    write_learning_path(vault, order, titles, filenames, levels, rel_sources, deps)
    write_foundational(vault, titles, filenames, levels, deps, rel_sources)
    write_paths(vault, titles, filenames, levels, deps, rel_sources)
    write_canvas(vault, order, titles, filenames, levels, deps, rel_sources)
    write_bibtex(vault, titles, urls)
    write_kanban(vault, rel_sources, titles, filenames, status_map)
    write_daily_snippet(vault, rel_sources)
    print(f"✓ refreshed UX files for {len(rows)} notes")
    return 0


def set_status(args) -> int:
    vault = Path(args.vault).expanduser()
    sources = vault / args.sources_dir
    target_text = args.target.lower()
    matches = []
    for note in sources.glob("*.md"):
        fields, body = split_frontmatter(
            note.read_text(encoding="utf-8", errors="replace"))
        haystack = " ".join(str(v) for v in fields.values()).lower() + " " + note.name.lower()
        if target_text in haystack:
            matches.append((note, fields, body))
    if not matches:
        print(f"✗ No note matches '{args.target}'", file=sys.stderr)
        return 1
    if len(matches) > 1:
        print(f"✗ {len(matches)} notes match; be more specific:", file=sys.stderr)
        for n, _, _ in matches:
            print(f"   - {n.name}", file=sys.stderr)
        return 1
    note, fields, body = matches[0]
    fields["status"] = args.status
    fields["updated"] = stamp()
    note.write_text(render_note(fields, body), encoding="utf-8")
    print(f"✓ {note.name}: status = {args.status}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Browser tabs -> Obsidian reading queue with a relationship graph")
    sub = p.add_subparsers(dest="cmd")
    imp = sub.add_parser("import", aliases=["i"], help="Import tabs into the vault")
    imp.add_argument("input")
    imp.add_argument("--vault")
    imp.add_argument("--config", help="JSON config file (default: ./config.json)")
    imp.add_argument("--preset", choices=list(PRESETS), help="fast | balanced | deep")
    imp.add_argument("--skills-dir", help="Directory of Markdown model skills")
    imp.add_argument("--sources-dir")
    imp.add_argument("--topics-dir")
    imp.add_argument("--max-topics", type=int)
    imp.add_argument("--topics")
    imp.add_argument("--llm", action="store_true", help="Use the local model")
    imp.add_argument("--no-relations", action="store_true",
                     help="Skip the relationship pass")
    imp.add_argument("--relations-only", action="store_true",
                     help="Only rebuild the relationship graph from existing notes")
    imp.add_argument("--descriptions-only", action="store_true",
                     help="Only regenerate long English descriptions from existing notes")
    imp.add_argument("--llm-rel-timeout", type=int,
                     help="Seconds allowed for the relationship pass")
    imp.add_argument("--llm-url")
    imp.add_argument("--llm-model")
    imp.add_argument("--llm-timeout", type=int)
    imp.add_argument("--llm-batch", type=int)
    imp.add_argument("--llm-max-tokens", type=int)
    imp.add_argument("--llm-rel-max-tokens", type=int)
    imp.add_argument("--dry-run", action="store_true")
    imp.add_argument("--force", action="store_true", help="Reprocess notes even if cached")
    imp.add_argument("--no-cache", action="store_true", help="Bypass the model response cache")
    imp.add_argument("--clear-cache", action="store_true", help="Delete cache and exit")
    imp.add_argument("--json-mode", action="store_true",
                     help="Ask the endpoint for JSON-only responses")
    imp.add_argument("--grammar-file", help="GBNF grammar file (llama.cpp)")
    imp.add_argument("--fetch-content", action="store_true",
                     help="Download and extract page/PDF text for better descriptions")
    imp.add_argument("--dedupe", action="store_true",
                     help="Group near-identical titles before processing")
    imp.add_argument("--favicons", action="store_true",
                     help="Download site favicons into the vault")
    imp.add_argument("--no-ux", action="store_true",
                     help="Do not write Kanban/buttons/daily snippet files")

    st = sub.add_parser("set-status", help="Change a note's status")
    st.add_argument("target")
    st.add_argument("--status", required=True, choices=STATUSES)
    st.add_argument("--vault", required=True)
    st.add_argument("--sources-dir", default="Fuentes")

    sub.add_parser("clear-cache", help="Delete cached model responses")
    ux = sub.add_parser("refresh-ux", help="Regenerate Obsidian UX files from notes")
    ux.add_argument("--vault", required=True)
    ux.add_argument("--sources-dir", default="Fuentes")

    val = sub.add_parser("validate", help="Use the model to filter junk notes and bad edges")
    val.add_argument("--vault", required=True)
    val.add_argument("--sources-dir", default="Fuentes")
    val.add_argument("--config")
    val.add_argument("--llm-url")
    val.add_argument("--llm-model")
    val.add_argument("--llm-timeout", type=int)
    val.add_argument("--dry-run", action="store_true")

    sub.add_parser("init-topics", help="Write a default topics.json").add_argument(
        "path", nargs="?", default="topics.json")
    sub.add_parser("init-example", help="Write an example tabs file").add_argument(
        "path", nargs="?", default="example_tabs.json")

    doctor = sub.add_parser("doctor", help="Check the environment")
    doctor.add_argument("--vault")
    doctor.add_argument("--config")
    doctor.add_argument("--topics")
    doctor.add_argument("--skills-dir")
    doctor.add_argument("--llm-url")

    search = sub.add_parser("search", help="Search notes in the vault")
    search.add_argument("query", nargs="+")
    search.add_argument("--vault", required=True)
    search.add_argument("--sources-dir", default="Fuentes")
    search.add_argument("--config")
    search.add_argument("--top", type=int, default=8)
    search.add_argument("--embeddings", action="store_true")
    search.add_argument("--llm-url")
    search.add_argument("--llm-model")

    ask = sub.add_parser("ask", help="Answer a question from the vault (RAG)")
    ask.add_argument("query", nargs="+")
    ask.add_argument("--vault", required=True)
    ask.add_argument("--sources-dir", default="Fuentes")
    ask.add_argument("--config")
    ask.add_argument("--llm-url")
    ask.add_argument("--llm-model")
    ask.add_argument("--llm-timeout", type=int)

    feed = sub.add_parser("feed", help="Fetch recent arXiv papers as a tabs file")
    feed.add_argument("--query", default="large language model")
    feed.add_argument("--max-results", type=int, default=25)
    feed.add_argument("--output", default="arxiv-tabs.json")

    zot = sub.add_parser("zotero", help="Export Zotero items as a tabs file")
    zot.add_argument("--output", default="zotero-tabs.json")

    rw = sub.add_parser("readwise", help="Export Readwise articles as a tabs file")
    rw.add_argument("--token")
    rw.add_argument("--output", default="readwise-tabs.json")

    watch = sub.add_parser("watch", help="Watch a folder and import new tabs files")
    watch.add_argument("--dir", dest="watch_dir", default="Inbox")
    watch.add_argument("--interval", type=int, default=30)
    watch.add_argument("--config")
    watch.add_argument("--llm", action="store_true")

    ev = sub.add_parser("eval", help="Compare notes against a labelled set")
    ev.add_argument("--vault", required=True)
    ev.add_argument("--sources-dir", default="Fuentes")
    ev.add_argument("--labels", default="eval/labels.json")
    return p


def resolve_options(args, require_vault: bool = True) -> bool:
    """Merge: built-in defaults -> named preset -> config.json -> CLI flags."""
    cfg = load_config(getattr(args, "config", None))
    preset = getattr(args, "preset", None) or cfg.get("preset") or DEFAULTS["preset"]
    values = dict(DEFAULTS)
    values.update(PRESETS.get(preset, {}))
    values.update(cfg)
    values["preset"] = preset
    for key in DEFAULTS:
        supplied = getattr(args, key, None)
        if supplied is not None:
            values[key] = supplied
        setattr(args, key, values[key])
    args.skills_text = load_skills(getattr(args, "skills_dir", None))
    if require_vault and not args.vault:
        print("✗ --vault is required (or set 'vault' in config.json)", file=sys.stderr)
        return False
    print(f"⚙ preset={args.preset} batch={args.llm_batch} "
          f"skills={len(args.skills_text)} chars")
    return True


def main() -> int:
    parser = build_parser()
    argv = sys.argv[1:]
    known = {"import", "i", "set-status", "init-topics", "init-example",
             "search", "ask", "doctor", "feed", "zotero", "readwise", "watch",
             "eval", "clear-cache", "refresh-ux", "validate", "-h", "--help"}
    if argv and not argv[0].startswith("-") and argv[0] not in known:
        argv = ["import"] + argv
    args = parser.parse_args(argv)
    if args.cmd == "import" and getattr(args, "clear_cache", False):
        print(f"✓ cache cleared ({clear_cache()} entries)")
        return 0
    _CACHE_STATE.disabled = bool(getattr(args, "no_cache", False))
    _CACHE_STATE.forced = bool(getattr(args, "force", False))
    if args.cmd in ("import", "i"):
        if not resolve_options(args):
            return 1
        return import_tabs(args)
    if args.cmd == "clear-cache":
        print(f"✓ cache cleared ({clear_cache()} entries)")
        return 0
    if args.cmd == "refresh-ux":
        return refresh_ux(args)
    if args.cmd == "validate":
        resolve_options(args)
        return validate_cmd(args)
    if args.cmd == "set-status":
        return set_status(args)
    if args.cmd == "doctor":
        resolve_options(args, require_vault=False)
        return run_doctor(args)
    if args.cmd == "search":
        resolve_options(args)
        return search_notes(args)
    if args.cmd == "ask":
        resolve_options(args)
        return ask_notes(args)
    if args.cmd == "feed":
        return feed_arxiv(args)
    if args.cmd == "zotero":
        return import_zotero(args)
    if args.cmd == "readwise":
        return import_readwise(args)
    if args.cmd == "watch":
        return run_watch(args)
    if args.cmd == "eval":
        return run_eval(args)
    if args.cmd == "init-topics":
        Path(args.path).write_text(
            json.dumps(DEFAULT_TOPICS, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"✓ Taxonomy written to {args.path}")
        return 0
    if args.cmd == "init-example":
        Path(args.path).write_text(
            json.dumps(EXAMPLE_TABS, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"✓ Example written to {args.path}")
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
