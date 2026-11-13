"""Vercel routing and the optional Supabase copy. The database is never contacted."""
import json
import os
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from app import risk, store
from app.http_path import api_path

ROOT = Path(__file__).resolve().parents[1]
KEYS = ("SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY")


class _Body:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return b"[]"


class DeployTests(unittest.TestCase):
    def setUp(self):
        self.saved = {key: os.environ.get(key) for key in KEYS}
        for key in KEYS:
            os.environ.pop(key, None)
        store.reset_cache()

    def tearDown(self):
        for key, value in self.saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        store.reset_cache()

    def test_missing_settings_leave_the_demo_on_the_files(self):
        board = {"ok": True, "learners": [{"id": "E10", "learner": "Bongani Sithole", "risk": 53, "overall": 57}]}
        store.remember(board, store.DATA)
        store.remember_week({"ok": True, "after": board, "changes": []})
        store.clear_week()
        self.assertIsNone(store.load_week())
        self.assertIsNone(store.credentials())

    def test_a_database_error_is_ignored(self):
        os.environ["SUPABASE_URL"] = "https://example.supabase.co"
        os.environ["SUPABASE_ANON_KEY"] = "anon-test"

        def boom(*args, **kwargs):
            raise urllib.error.URLError("down")

        with mock.patch("urllib.request.urlopen", boom):
            store.remember({
                "ok": True,
                "learners": [{
                    "id": "E10", "learner": "Bongani Sithole", "risk": 53, "overall": 57,
                    "band": "High", "result": "Pass", "reason": "practical gaps",
                    "theory": {}, "practical": {"outcomes": []}, "windows": [],
                }],
            })
            self.assertIsNone(store.load_week())
            store.clear_week()

    def test_writes_use_the_service_key_and_the_demo_names(self):
        os.environ["SUPABASE_URL"] = "https://example.supabase.co"
        os.environ["SUPABASE_ANON_KEY"] = "anon-test"
        os.environ["SUPABASE_SERVICE_ROLE_KEY"] = "service-test"
        seen = []

        def fake(req, timeout=0):
            seen.append((req.full_url, req.data, req.headers["Authorization"]))
            return _Body()

        with mock.patch("urllib.request.urlopen", fake):
            board = risk.assess(store.DATA)
            store.remember(board, store.DATA)
        self.assertGreaterEqual(len(seen), 4)
        posted = b"".join(body or b"" for _, body, _ in seen).decode()
        self.assertIn("Sipho Ndlovu", posted)
        self.assertIn("Ruan Botha", posted)
        self.assertIn("Bongani Sithole", posted)
        self.assertIn('"risk": 53', posted)
        self.assertIn('"overall": 57', posted)
        self.assertIn('"id": "H1"', posted)
        self.assertIn('"id": "S1"', posted)
        self.assertTrue(all(auth == "Bearer service-test" for _, _, auth in seen))
        self.assertTrue(all("anon-test" not in url for url, _, _ in seen))

    def test_week_two_rescue_is_stored_when_the_database_answers(self):
        os.environ["SUPABASE_URL"] = "https://example.supabase.co"
        os.environ["SUPABASE_SERVICE_ROLE_KEY"] = "service-test"
        seen = []

        def fake(req, timeout=0):
            seen.append((req.full_url, req.data))
            if req.full_url.endswith("week_runs?id=eq.1&select=payload"):
                return _Json(b'[{"payload": {"ok": true, "summary": "kept"}}]')
            return _Body()

        with mock.patch("urllib.request.urlopen", fake):
            store.remember_week({
                "ok": True,
                "summary": "Week 2 reran the loop.",
                "changes": [{
                    "id": "E10", "risk_before": 53, "risk_after": 22,
                    "band_before": "High", "band_after": "Low",
                    "overall_before": 57, "overall_after": 78,
                    "result_before": "Pass", "result_after": "Pass",
                }],
                "after": {
                    "learners": [{
                        "id": "E10", "learner": "Bongani Sithole", "risk": 22, "overall": 78,
                        "band": "Low", "result": "Pass", "reason": "after the rescue week",
                        "theory": {"percent": 70}, "practical": {"outcomes": [{"id": "H3", "percent": 80, "detail": "RAM"}]},
                        "windows": [{"id": "S4", "percent": 80, "detail": "device"}],
                    }],
                },
            })
            store.reset_cache()
            loaded = store.load_week()
        self.assertEqual(loaded["summary"], "kept")
        rescue = next(body.decode() for url, body in seen if url.endswith("/rescue_plans") and body)
        self.assertIn('"risk_before": 53', rescue)
        self.assertIn('"risk_after": 22', rescue)
        self.assertIn('"overall_before": 57', rescue)
        self.assertIn('"overall_after": 78', rescue)

    def test_migration_seeds_the_same_week_two_story(self):
        schema = (ROOT / store.MIGRATION).read_text(encoding="utf-8")
        seed = (ROOT / store.SEED).read_text(encoding="utf-8")
        self.assertEqual(schema, store.schema_sql())
        self.assertEqual(seed, store.seed_sql())
        self.assertIn("enable row level security", schema)
        self.assertNotIn("Sipho Ndlovu", schema)
        self.assertNotIn("insert into", schema.lower())
        self.assertIn("Sipho Ndlovu", seed)
        self.assertIn("Ruan Botha", seed)
        self.assertIn("Bongani Sithole", seed)
        self.assertRegex(
            seed,
            r"\(\$labless\$E10\$labless\$, \$labless\$.*\$labless\$, 53, 22, \$labless\$High\$labless\$, "
            r"\$labless\$Low\$labless\$, 57, 78, \$labless\$Pass\$labless\$, \$labless\$Pass\$labless\$\)",
        )

    def test_vercel_builds_the_static_site_and_one_python_function(self):
        cfg = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
        self.assertEqual(cfg["outputDirectory"], "web/dist")
        self.assertIn("npm run build --prefix web", cfg["buildCommand"])
        self.assertTrue(any(item["source"].startswith("/api") for item in cfg["rewrites"]))
        entry = (ROOT / "api" / "index.py").read_text(encoding="utf-8")
        self.assertIn("class handler(Handler)", entry)
        for name in ("requirements.txt", "api/requirements.txt"):
            packages = [
                line.strip() for line in (ROOT / name).read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.strip().startswith("#")
            ]
            self.assertEqual(packages, [])
        example = (ROOT / ".env.example").read_text(encoding="utf-8").lower()
        for banned in ("eyj", "sb_", "sk-"):
            self.assertNotIn(banned, example)
        example = (ROOT / ".env.example").read_text(encoding="utf-8")
        for name in ("SUPABASE_URL=", "SUPABASE_ANON_KEY=", "SUPABASE_SERVICE_ROLE_KEY="):
            self.assertIn(name, example)
        for line in example.splitlines():
            if "=" in line and not line.strip().startswith("#"):
                self.assertEqual(line.split("=", 1)[1].strip(), "")

    def test_rewritten_api_paths_keep_the_query(self):
        self.assertEqual(api_path("/api/state?since=4"), "/api/state?since=4")
        self.assertEqual(api_path("/api/index?route=state&since=4"), "/api/state?since=4")
        self.assertEqual(api_path("/api/index?route=ingest&sample=1"), "/api/ingest?sample=1")
        self.assertEqual(api_path("/api/index?route=corrections.md"), "/api/corrections.md")
        self.assertEqual(
            api_path("/api/index", {"x-forwarded-uri": "/api/week2"}),
            "/api/week2",
        )


class _Json(_Body):
    def __init__(self, raw):
        self.raw = raw

    def read(self):
        return self.raw


if __name__ == "__main__":
    unittest.main()
