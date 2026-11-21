# Quick start (5 minutes)

## 1. Install the pieces

- Python 3.8+ (no `pip install` needed).
- A local model server: `llama-server`, Ollama, vLLM or LM Studio.
- Obsidian with the **Dataview** community plugin (for the dashboard tables).

## 2. Get your tabs out of Chromium

1. Open `chrome://extensions`, enable **Developer mode**.
2. **Load unpacked** → select the `extension/` folder.
3. Click the extension icon.
4. Choose **Current window**, or tick one or more **tab groups**, then:
   - **Download JSON** saves `tabs-*.json`,
   - **Copy JSON** puts the same payload on the clipboard,
   - **Copy as Markdown links** is handy for sharing.

Options: remove duplicate URLs, skip `chrome://`/localhost pages, and write one
file per group.

No Chromium? Create `urls.txt` with one URL per line (optionally
`Title | URL`), or export your bookmarks as HTML. All three formats are accepted.

## 3. Start the local model

```bash
./start-local-model.sh          # uses the bundled GGUF on port 8080
```

For Ollama: `ollama serve` and pass
`--llm-url http://127.0.0.1:11434/v1/chat/completions --llm-model <name>`.

Check it: `curl http://127.0.0.1:8080/health` → `{"status":"ok"}`.

## 4. Import

```bash
cp config.example.json config.json      # set your vault path
./run.sh tabs-2026-11-21.json all       # serve (if needed) + import + open Obsidian
```

Or run the steps manually:

```bash
python3 tabs_to_obsidian.py import tabs.json \
  --vault ~/Documents/Obsidian\ Vault --llm --preset balanced
```

The first run is the slow one: 72 sources take about 20–30 minutes on CPU
(two model passes). Re-importing is fast and preserves your edits.

## 5. Read the result in Obsidian

- Open `00-Learning Path.md` — start at **Level 1** and follow the numbered list.
  Notes link to their prerequisites, and the small Mermaid graph shows the first
  dependency chain.
- Open `00-Dashboard.md` — the queue by status. Change any note's state from the
  **Properties** panel (`status`: `queued` → `reading` → `read` → `archived`).
- Open the **Graph view** (top-right icon) — each note connects to its topic
  nodes and to related/prerequisite notes.
- Open `MOC-LLMs.md` for the full index.

## 6. Refresh later

```bash
# new tabs, same workflow
./run.sh new-tabs.json full

# only rebuild the relationship graph (much faster)
./run.sh new-tabs.json relations

# only rewrite long descriptions
./run.sh new-tabs.json descriptions
```
