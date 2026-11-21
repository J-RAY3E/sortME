# Model skills

"Skills" are small Markdown files with instructions that are appended to the
model's system prompt at import time. They let you change **how the data is
treated** without editing Python.

## Included skills

| File | What it controls |
|---|---|
| `00-description-style.md` | English, three parts, no marketing language, no invented facts |
| `01-topic-mapping.md` | Prefer specific topics, exact names, "General" last |
| `02-relationships.md` | What counts as a real prerequisite vs. a related note |
| `03-levels.md` | How to calibrate difficulty from 1 to 5 |
| `04-data-hygiene.md` | Keep titles verbatim, ignore tracking params, strict JSON |

## How they are used

On startup the importer reads every `*.md` in the skills directory in filename
order and joins them:

```text
You are a research librarian ... (base system prompt)

--- SKILL: 00-description-style ---
...

--- SKILL: 01-topic-mapping ---
...
```

The base prompt always requires **valid JSON only, in English**. Keep that rule
intact when authoring your own skills.

## Add your own

```bash
cat > skills/05-my-rules.md <<'EOF'
# Skill: my rules

- Always prefer primary sources (arXiv, conference proceedings) over blogs when
  choosing a prerequisite.
- Never mark a LeetCode problem as a prerequisite for a research paper.
EOF

python3 tabs_to_obsidian.py import tabs.json --vault <vault> --llm
```

Point at a different directory with `--skills-dir /path/to/skills`, or set
`"skills_dir"` in config. Pass an empty directory to disable all skills.

## Troubleshooting skills

The startup line `⚙ preset=balanced batch=6 skills=NNNN chars` tells you how
much skill text was loaded. If it says `0`, the directory does not exist or is
empty. Keep the total reasonably small (a few thousand characters) so it does
not crowd out the catalog in the relationship pass.
