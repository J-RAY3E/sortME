# Architecture

## Pipeline

```
tabs.json / urls.txt / bookmarks.html
        |
        v
read_tabs()  --->  note identity = slug(title) + sha1(url)[:8]
        |
        +-- pass 1: llm_describe_all()
        |     per batch: topics[], level 1-5, problem/method/takeaway
        |     joined into a ~90-word English description
        |
        +-- pass 2: llm_relations()
              compact catalog of ALL notes (index, short title, topics)
              returns per note: level, pre[], rel[]
        |
        v
topological_order()  -- Kahn's algorithm, cycles broken by (level, index)
        |
        v
write notes + topic notes + MOC + dashboard + learning path
```

## Files written to the vault

| Path | Generator | Purpose |
|---|---|---|
| `Fuentes/<slug>-<hash>.md` | `import_tabs` | Source note with frontmatter and wikilinks |
| `Temas/<Topic>.md` | `write_topic_notes` | Topic node with a Dataview query |
| `MOC-LLMs.md` | `write_moc` | Index of topics and all sources |
| `00-Dashboard.md` | `write_dashboard` | Status queue with Dataview tables |
| `00-Learning Path.md` | `write_learning_path` | Ordered path + Mermaid graph |

## Frontmatter of a source note

```yaml
title: "Attention Is All You Need"
url: "https://arxiv.org/abs/1706.03762"
source: "paper"
description: "..."          # English, problem + method + takeaway
level: 2
status: "queued"            # queued | reading | read | archived
priority: "medium"
topics: ["Transformers & Attention"]
tags: ["llm", "transformers"]
prerequisites: ["another-note.md"]
related: ["other-note.md"]
created: "2026-11-21"
updated: "2026-11-21T20:00:00Z"
user_notes: ""
```

`status`, `priority`, `created` and `user_notes` survive re-imports.

## Why two passes?

The relationship pass needs the whole catalog to choose meaningful edges, but
the description pass is more accurate in small batches. Separating them also
lets you rebuild either one independently with `--descriptions-only` or
`--relations-only`, which matters when the local model is slow.

## Failure modes

- A model batch fails or times out → keyword fallback for descriptions, or
  topic-overlap ordering for the path. The import still completes.
- A model returns invalid JSON → `extract_json()` tries the whole string, then
  the outermost object, then the array, before giving up.
- A topic note is removed from `topics.json` → its generated file is deleted on
  the next import (only files with `topic:` frontmatter are touched).
