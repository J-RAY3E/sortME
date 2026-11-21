# Configuration & presets

Settings are resolved in this order (later wins):

```
built-in defaults  ->  named preset  ->  config.json  ->  CLI flags
```

## config.json

Copy `config.example.json` to `config.json` and edit. Any field can also be
passed on the command line.

```json
{
  "vault": "/home/azawa/Documents/Obsidian Vault",
  "sources_dir": "Fuentes",
  "topics_dir": "Temas",
  "preset": "balanced",
  "skills_dir": "skills",
  "llm": {
    "url": "http://127.0.0.1:8080/v1/chat/completions",
    "model": "local-llm",
    "timeout": 300,
    "rel_timeout": 900
  }
}
```

Nested `llm.*` keys map to `--llm-url`, `--llm-model`, `--llm-timeout` and
`--llm-rel-timeout`.

## Presets

| Preset | Batch | Max tokens (desc / rel) | Topics | Timeouts (desc / rel) |
|---|---|---|---|---|
| `fast` | 12 | 2048 / 2048 | 2 | 180 s / 600 s |
| `balanced` (default) | 6 | 2048 / 3072 | 3 | 300 s / 900 s |
| `deep` | 4 | 3072 / 4096 | 4 | 420 s / 1200 s |

Use `--preset fast|balanced|deep` or set `"preset"` in the config.

- **fast** — fewer requests, shorter output, good for a first pass.
- **balanced** — the default used on the 72-tab sample.
- **deep** — smaller batches and more tokens per answer; slowest but most
  detailed. Use when you have GPU acceleration.

## CLI reference

```
python3 tabs_to_obsidian.py import INPUT [options]

  --vault PATH             Obsidian vault (or config)
  --config PATH            config file (default ./config.json)
  --preset NAME            fast | balanced | deep
  --skills-dir PATH        directory of Markdown model skills
  --sources-dir NAME       notes folder (default Fuentes)
  --topics-dir NAME        topic folder (default Temas)
  --max-topics N           topics per note
  --topics PATH            custom taxonomy JSON

  --llm                    run the local-model pipeline
  --llm-url URL            OpenAI-compatible endpoint
  --llm-model NAME         model alias
  --llm-timeout N          seconds per description batch
  --llm-rel-timeout N      seconds for the relationship pass
  --llm-batch N            sources per description request
  --llm-max-tokens N       token cap for descriptions
  --llm-rel-max-tokens N   token cap for relationships

  --descriptions-only      regenerate descriptions only
  --relations-only         rebuild the note graph only
  --no-relations           skip pass 2
  --dry-run                preview counts, write nothing

python3 tabs_to_obsidian.py set-status TARGET --status QUEUED|READING|READ|ARCHIVED --vault PATH
python3 tabs_to_obsidian.py init-topics [path]
python3 tabs_to_obsidian.py init-example [path]
```

## Orchestrator modes

```bash
./run.sh tabs.json all            # start model (if needed), full import, open Obsidian
./run.sh tabs.json serve          # only start the model
./run.sh tabs.json full           # descriptions + relationships
./run.sh tabs.json fast|deep      # named preset
./run.sh tabs.json descriptions   # only descriptions
./run.sh tabs.json relations      # only relationship graph
./run.sh tabs.json open           # only open the vault
```

Environment overrides for the server: `CTX` (context size, default 8192),
`NGL` (GPU layers, default 0), `MODEL`, `PORT`, `CONFIG`.

## Advanced import flags

| Flag | Effect |
|---|---|
| `--force` | Reprocess every note, ignoring fingerprints and cache |
| `--no-cache` | Bypass the disk cache for this run |
| `--clear-cache` | Delete all cached model responses |
| `--json-mode` | Send `response_format: {"type":"json_object"}` |
| `--grammar-file PATH` | Send a GBNF grammar to llama.cpp |
| `--fetch-content` | Download pages/PDFs and use their text in prompts |
| `--dedupe` | Group near-identical titles before processing |
| `--favicons` | Download favicons into the vault |
| `--no-ux` | Skip Kanban, buttons, Canvas, paths, BibTeX and snippet files |

## Other subcommands

```
doctor                         environment check
clear-cache                    delete cached model responses
search QUERY --vault PATH      TF-IDF search (--embeddings for vectors)
ask QUERY --vault PATH         RAG answer from your notes
feed --query Q --output FILE   arXiv feed -> tabs file
zotero --output FILE           local Zotero API -> tabs file
readwise --token T --output F  Readwise API -> tabs file
watch --dir DIR --interval N   auto-import dropped tabs files
eval --vault PATH --labels F   compare notes with ground truth
```

See [ADVANCED.md](ADVANCED.md) for details.

## Taxonomy

`topics.json` is a plain object:

```json
"RAG": {
  "tag": "rag",
  "keywords": ["rag", "retrieval", "vector database", "chunking"]
}
```

Edit it to add or remove subjects. The importer removes generated topic notes
that are no longer in the taxonomy. Reset with
`python3 tabs_to_obsidian.py init-topics topics.json`.
