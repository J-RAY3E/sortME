"""Offline tests: mock OpenAI-compatible server, no real model needed."""
import json
import re
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tabs_to_obsidian as app

TEXT = ("This source explains the core mechanism in detail and walks through the "
        "motivating problem, the main technical contribution, and the practical "
        "trade-offs involved. It compares the approach with earlier work, shows "
        "representative results, and closes with open problems and pointers to "
        "implementations for further reading.")


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        prompt = req["messages"][-1]["content"]
        if "CATALOG (" in prompt:
            catalog = json.loads(re.search(
                r"CATALOG \(\d+ notes\):\n(\[.*?\])\n\n", prompt, re.S).group(1))
            rows = [{"i": e["i"], "level": 2, "pre": [], "rel": [], "conf": 0.9}
                    for e in catalog]
        else:
            entries = json.loads(re.search(
                r"SOURCES:\n(\[.*?\])\n\n", prompt, re.S).group(1))
            rows = [{"i": e["i"], "topics": ["RAG"], "level": 2,
                     "problem": TEXT, "method": TEXT, "takeaway": TEXT}
                    for e in entries]
        out = {"results": rows} if "SOURCES:" in prompt else {"nodes": rows}
        payload = json.dumps({"choices": [{"message": {
            "content": "```json\n" + json.dumps(out) + "\n```"}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass


class PipelineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.vault = Path(self.tmp.name) / "vault"
        self.url = f"http://127.0.0.1:{self.port}/v1/chat/completions"
        app._CACHE_STATE.disabled = True
        app._CACHE_STATE.forced = False

    def tearDown(self):
        self.tmp.cleanup()

    def args(self, **overrides):
        values = dict(
            input="example_tabs.json", vault=str(self.vault),
            sources_dir="Fuentes", topics_dir="Temas", topics=None,
            max_topics=3, preset="balanced", skills_dir=None,
            llm=True, no_relations=False, relations_only=False,
            descriptions_only=False, llm_url=self.url, llm_model="mock",
            llm_timeout=30, llm_rel_timeout=30, llm_batch=4,
            llm_max_tokens=1024, llm_rel_max_tokens=1024,
            dry_run=False, force=False, no_cache=True, clear_cache=False,
            json_mode=False, grammar_file=None, fetch_content=False,
            dedupe=False, favicons=False, no_ux=False,
        )
        values.update(overrides)
        app.resolve_options(type("A", (), values)())
        return type("A", (), values)()

    def test_import_creates_all_artifacts(self):
        args = self.args()
        self.assertEqual(app.import_tabs(args), 0)
        for name in ("00-Dashboard.md", "00-Learning Path.md", "MOC-LLMs.md",
                     "00-Foundational Notes.md", "00-Knowledge Map.canvas",
                     "00-Queue Kanban.kanban", "references.bib",
                     "00-Daily Queue Snippet.md"):
            self.assertTrue((self.vault / name).exists(), name)
        notes = list((self.vault / "Fuentes").glob("*.md"))
        self.assertEqual(len(notes), 9)
        self.assertIn("Description", notes[0].read_text())

    def test_incremental_skips_model(self):
        self.assertEqual(app.import_tabs(self.args()), 0)
        args = self.args()
        self.assertEqual(app.import_tabs(args), 0)
        fields, _ = app.split_frontmatter(
            next((self.vault / "Fuentes").glob("*.md")).read_text())
        self.assertTrue(fields.get("ai_fingerprint"))

    def test_dedupe(self):
        tabs = [{"title": "Attention Is All You Need", "url": "https://a/1"},
                {"title": "Attention Is All You Need (v2)", "url": "https://a/2"},
                {"title": "RAG for NLP", "url": "https://b/1"}]
        kept, dups = app.deduplicate_tabs(tabs)
        self.assertEqual(len(kept), 2)
        self.assertEqual(len(dups["https://a/1"]), 1)

    def test_json_extraction_bare_array(self):
        parsed = app.extract_json('```json\n[{"i":0,"level":1}]\n```')
        self.assertIsInstance(parsed, list)

    def test_fingerprint_stable(self):
        self.assertEqual(app.fingerprint("a", "b"), app.fingerprint("a", "b"))
        self.assertNotEqual(app.fingerprint("a", "b"), app.fingerprint("a", "c"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
