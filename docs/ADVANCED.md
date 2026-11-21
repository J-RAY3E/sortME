# Advanced features

## Cache and incremental import

Every model request is cached on disk under `.cache/<kind>/<hash>.json`. The key
includes the prompt, model, endpoint and `PROMPT_VERSION`, so changing a skill
or a prompt automatically invalidates old answers.

```bash
python3 tabs_to_obsidian.py clear-cache
python3 tabs_to_obsidian.py import tabs.json --vault ... --no-cache   # bypass once
python3 tabs_to_obsidian.py import tabs.json --vault ... --force      # redo everything
```

Each note stores `ai_fingerprint` and `relation_fingerprint`. On the next import
only changed sources go to the model, and the relationship pass is skipped when
the graph has not changed. Expected output on a second run:

```
↻ incremental: 0/71 sources need the model
↻ relationships unchanged (cached)
```

## Content ingestion

By default the model sees only the title and URL. With `--fetch-content` the
importer downloads each page (or PDF), extracts text and includes the first
1500 characters in the description prompt:

```bash
python3 tabs_to_obsidian.py import tabs.json --vault ... --llm --fetch-content
```

PDFs need `pdftotext` (poppler-utils). Failures are silent and fall back to
title-only. Fetched text is cached separately, so repeated runs are cheap.
Notes get a `read_minutes` estimate based on the extracted word count.

## Semantic deduplication

`--dedupe` groups titles with a similarity ratio ≥ 0.82 (same paper on arXiv,
PDF mirror and blog post). Only one note per group gets a description; the
other URLs are stored in the `duplicates` frontmatter field.

## JSON mode and grammar

Some models wrap JSON in fences or return bare arrays (both are handled).
For stricter decoding:

```bash
python3 tabs_to_obsidian.py import tabs.json --vault ... --llm \
  --json-mode --grammar-file grammar/json.gbnf
```

`--json-mode` sends `response_format: {"type":"json_object"}`;
`--grammar-file` sends a GBNF grammar. Both are passed straight to the
OpenAI-compatible endpoint (supported by llama.cpp; other backends may ignore
them).

## Graph analytics

The importer writes three graph-derived views:

- **`00-Foundational Notes.md`** — top 10 notes by in-degree (how many other
  notes list them as prerequisites).
- **`Paths/To *.md`** — for the five most-targeted notes, the full reverse
  prerequisite chain in reading order.
- **`00-Knowledge Map.canvas`** — every note placed at `x = level * 420` with
  arrows for prerequisite edges. Open it in Obsidian Canvas.

Edges with a model confidence below 0.6 can be removed by setting
`relation_confidence` in the note frontmatter; the generators read the current
graph from the notes on every run.

## Obsidian UX files

- **Status buttons** — each note ends with a folded `[!tip] Quick status`
  callout containing DataviewJS buttons. Enable **Settings → Plugins →
  Dataview → Enable JavaScript Queries** first. The buttons call
  `app.fileManager.processFrontMatter` on the current file.
- **`00-Queue Kanban.kanban`** — a board with the four statuses. Install the
  `obsidian-kanban` community plugin. The importer regenerates it from the
  current `status` values on each run; inside Obsidian, drag-and-drop edits it.
- **`00-Daily Queue Snippet.md`** — a small Dataview query to paste into your
  daily note.
- **`references.bib`** — BibTeX `@misc` entries with arXiv-derived years.

Disable all of these with `--no-ux` if you only want the core notes.

Favicons: `--favicons` downloads each site's icon into `Fuentes/icons/` and
adds an `icon` property to the note.

## Search and RAG

```bash
# lexical (TF-IDF, always available, no model needed)
python3 tabs_to_obsidian.py search "chunking strategies" --vault ... --top 5

# vector (needs an embedding-capable endpoint)
python3 tabs_to_obsidian.py search "chunking" --vault ... --embeddings

# answer a question from your notes
python3 tabs_to_obsidian.py ask "What does the RAG paper propose?" --vault ...
```

`--embeddings` posts to the `/v1/embeddings` endpoint derived from `--llm-url`
and ranks by cosine similarity. If the server was not started with embedding
support, it falls back to TF-IDF with a warning. Start llama-server with
`--embedding` if you want vector search.

`ask` retrieves the five most relevant notes, injects their descriptions and
first 800 characters into a prompt, and returns a sourced answer in English.

## Feeders and automation

```bash
# arXiv -> tabs file, then import it
python3 tabs_to_obsidian.py feed --query "LLM agents" --max-results 30 \
  --output arxiv-tabs.json
python3 tabs_to_obsidian.py import arxiv-tabs.json --vault ... --llm

# Zotero (local API, requires Zotero running)
python3 tabs_to_obsidian.py zotero --output zotero-tabs.json

# Readwise
python3 tabs_to_obsidian.py readwise --token "$READWISE_TOKEN" --output rw.json

# watch an inbox folder
python3 tabs_to_obsidian.py watch --dir Inbox --interval 30 --llm --config config.json
```

For a background service, copy `systemd/sortme-watch.service` to
`~/.config/systemd/user/`, edit the paths, then:

```bash
systemctl --user daemon-reload
systemctl --user enable --now sortme-watch.service
```

## Model-based validation

A second use of the same local model cleans the graph instead of creating it:

```bash
python3 tabs_to_obsidian.py validate --vault /path/to/vault --dry-run
python3 tabs_to_obsidian.py validate --vault /path/to/vault
```

Two passes:

1. **Note pass** — every note is judged `keep: true|false`. Generic coding
   challenges, video/anime sites, product console pages and vague one-word
   entries get archived (`excluded: true`, `status: archived`).
2. **Edge pass** — every prerequisite/related edge is judged independently and
   weak links are removed.

A deterministic rule set (`JUNK_TITLE_PATTERNS` in the script) also archives
 obvious titles like `ChatGPT`, `LeetCode` or `Daily Temperatures` even if the
 model is lenient. Archived notes are excluded from every generated view.

The command regenerates all UX files afterwards, so the learning path, Canvas,
status page and graph overview reflect the cleaned graph immediately.

## Plugin-free status and organised graph

- **`00-Status.md`** is plain Markdown (no Dataview required): counts plus a
  table per status with clickable note links. Open a note and edit `status` in
  the Properties panel to move it between columns.
- **`00-Graph Overview.md`** presents the graph as Mermaid **subgraphs grouped
  by topic**, with prerequisite arrows between visible nodes, followed by a
  level pyramid and links to the interactive views.
- If Dataview does not render, `refresh-ux` regenerates these files directly
  from the notes' frontmatter without calling the model:

```bash
python3 tabs_to_obsidian.py refresh-ux --vault /path/to/vault
```

## Doctor and evaluation

```bash
python3 tabs_to_obsidian.py doctor --vault /path/to/vault
python3 tabs_to_obsidian.py eval --vault /path/to/vault --labels eval/labels.json
```

`doctor` checks Python, taxonomy, skills, vault, Dataview and model health.
`eval` compares a set of notes against `eval/labels.json` (expected topics and
an expected related-note fragment). Edit that file with your own ground truth
to compare `fast`, `balanced` and `deep` objectively.

## Tests and CI

```bash
python3 -m unittest discover -s tests -v
```

The suite starts a mock OpenAI-compatible server on a random port and verifies
artifact generation, incremental import, deduplication and JSON parsing — no
model or network required. `.github/workflows/tests.yml` runs it on every push
along with a syntax check and JSON validation.
