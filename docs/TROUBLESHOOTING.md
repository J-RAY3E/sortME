# Troubleshooting

## The model

**`couldn't bind HTTP server socket ... port 8080`** — another server is still
running. `pkill -f llama-server`, wait two seconds, then start again.

**Relationship pass times out** — it is the longest request. Raise
`--llm-rel-timeout` (default 900 s) or use the `fast` preset. You can always
rebuild only the graph with `--relations-only`.

**Descriptions too short** — the model does not follow word counts reliably.
This project asks for three separate parts (`problem`, `method`, `takeaway`) and
joins them; if yours still come out short, strengthen
`skills/00-description-style.md` and re-run `--descriptions-only`.

**`✗ the model returned no relations`** — the JSON was truncated. Increase
`--llm-rel-max-tokens` or lower the number of notes by splitting the catalog.

## Obsidian

**Dashboard shows raw code blocks** — install the Dataview community plugin,
then restart Obsidian or toggle the plugin off/on.

**"Do you trust the author of this vault?"** — accept it, otherwise community
plugins stay disabled.

**Graph view is empty** — open `MOC-LLMs.md` first so topic links are resolved,
then open Graph view. Disable "Show attachments" if needed.

**New files do not appear** — Obsidian normally detects them automatically;
otherwise restart the app.

## Extension

**`chrome://extensions` looks empty** — that just means you have no extensions.
Find the **Developer mode** toggle in the top-right corner, then **Load
unpacked** appears at the top-left. Select the `extension/` folder.

**No tab groups listed** — groups are a Chromium feature. In Firefox only
"Current window" is available. Make sure the tabs are in the same window.

**Some tabs are missing** — the extension skips `chrome://`, `localhost` and
duplicates by default. Untick those options if you need them.

## Import

**`--vault is required`** — pass `--vault PATH` or set `vault` in config.json.

**Notes are not duplicated** — that is intentional: they are keyed by URL hash.
Status and your own notes are preserved. Use a different `sources_dir` if you
want a separate copy.

**Many notes land in General** — add keywords to `topics.json`, import
`skills/01-topic-mapping.md` guidance, or run the `deep` preset.
