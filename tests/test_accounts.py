"""Teacher accounts.  Run:  python -m unittest discover tests

Against a stand-in Supabase (tests/fake_supabase.py), which keeps rows to their owner the way the row level
security policies do. These tests prove the server checks each token, acts with that teacher's own token,
and that teacher B cannot see teacher A's runs. The policies themselves are SQL in supabase/migrations.
"""
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

os.environ["MOCK_DELAY"] = "0"
os.environ["MOCK"] = "1"

import run as server  # noqa: E402
from app import accounts  # noqa: E402
from tests import fake_supabase  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


class Accounts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fake, cls.store = fake_supabase.serve()
        cls.env = mock.patch.dict(os.environ, {"SUPABASE_URL": f"http://127.0.0.1:{cls.fake.server_address[1]}", "SUPABASE_ANON_KEY": fake_supabase.ANON})
        cls.env.start()
        server.OUTPUT = Path(tempfile.mkdtemp())
        cls.httpd = server.Server(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.fake.shutdown()
        cls.env.stop()

    def setUp(self):
        accounts._users.clear()

    def call(self, path, body=None, token=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(self.base + path, data=None if body is None else json.dumps(body).encode(), headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def teacher(self, email, name):
        req = urllib.request.Request(f"{os.environ['SUPABASE_URL']}/auth/v1/signup", method="POST",
                                     data=json.dumps({"email": email, "password": "secret123", "data": {"display_name": name}}).encode(),
                                     headers={"apikey": fake_supabase.ANON, "Content-Type": "application/json"})
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())["access_token"]

    def test_config_gives_the_browser_only_public_values(self):
        code, cfg = self.call("/api/config")
        self.assertEqual(code, 200)
        self.assertEqual(set(cfg), {"auth", "supabase_url", "anon_key"})
        self.assertTrue(cfg["auth"])
        with mock.patch.dict(os.environ, {"SUPABASE_SERVICE_ROLE_KEY": "very-secret"}):
            self.assertNotIn("very-secret", json.dumps(self.call("/api/config")[1]))
        with mock.patch.dict(os.environ, {"SUPABASE_URL": ""}):
            self.assertEqual(self.call("/api/config")[1], {"auth": False})

    def test_a_missing_or_bad_token_is_refused(self):
        self.assertEqual(self.call("/api/me")[0], 401)
        self.assertEqual(self.call("/api/me", token="not-a-real-token")[0], 401)
        self.assertEqual(self.call("/api/runs", {"id": "r1"}, token="not-a-real-token")[0], 401)

    def test_teacher_b_cannot_see_teacher_a(self):
        a = self.teacher("a@school.example", "Ms A")
        b = self.teacher("b@school.example", "Mr B")
        self.store.seen_auth.clear()
        self.assertEqual(self.call("/api/runs", {"id": "run-a", "goal": "Mark the essays.", "marked": 11, "when": 1}, token=a)[0], 200)
        self.assertEqual(self.call("/api/classes/sample", {}, token=a)[0], 200)
        self.assertEqual(self.call("/api/profile", {"display_name": "Ms Ayanda", "school": "Rosebank High"}, token=a)[0], 200)
        me_a = self.call("/api/me", token=a)[1]
        me_b = self.call("/api/me", token=b)[1]
        self.assertEqual([r["id"] for r in me_a["runs"]], ["run-a"])
        self.assertEqual(len(me_a["classes"]), 1)
        self.assertEqual(me_a["profile"]["display_name"], "Ms Ayanda")
        self.assertEqual((me_b["runs"], me_b["classes"]), ([], []))
        self.assertEqual(me_b["profile"]["display_name"], "Mr B")
        # Every database call was made with a teacher's own token, never a shared key.
        self.assertTrue(self.store.seen_auth)
        self.assertTrue(all(h in (f"Bearer {a}", f"Bearer {b}") for h in self.store.seen_auth))

    def test_a_run_is_seen_only_by_the_teacher_who_started_it(self):
        a = self.teacher("d@school.example", "Ms D")
        b = self.teacher("e@school.example", "Mr E")
        code, _ = self.call("/api/run", {"goal": "Mark the essays and send every learner feedback."}, token=a)
        self.assertEqual(code, 200)
        run = server.current["run"]
        run.work.acquire()  # wait for it to finish
        run.work.release()
        self.assertEqual(self.call("/api/state", token=a)[1]["id"], run.id)
        for other in (b, None):  # another teacher, and a guest, see an empty desk
            state = self.call("/api/state", token=other)[1]
            self.assertEqual((state["id"], state["status"]), (None, "idle"))
            self.assertEqual(self.call("/api/resolve", {"id": "E01", "choice": "marker"}, token=other)[0], 404)
        with urllib.request.urlopen(urllib.request.Request(f"{self.base}/api/file?name=marks.csv", headers={"Authorization": f"Bearer {a}"})) as r:
            self.assertEqual(r.status, 200)
        with self.assertRaises(urllib.error.HTTPError):
            urllib.request.urlopen(urllib.request.Request(f"{self.base}/api/file?name=marks.csv", headers={"Authorization": f"Bearer {b}"}))
        server.current["run"] = None

    def test_saving_the_same_run_twice_keeps_one_row(self):
        a = self.teacher("c@school.example", "Ms C")
        for marked in (5, 11):
            self.call("/api/runs", {"id": "run-c", "goal": "x", "marked": marked, "when": 1}, token=a)
        runs = self.call("/api/me", token=a)[1]["runs"]
        self.assertEqual([(r["id"], r["marked"]) for r in runs], [("run-c", 11)])

    def test_the_migration_keeps_every_new_table_to_its_owner(self):
        sql = next((ROOT / "supabase" / "migrations").glob("*_accounts.sql")).read_text(encoding="utf-8")
        for table in ("classes", "class_learners", "submissions", "runs", "run_events", "messages", "uploads"):
            self.assertIn(f"create table if not exists public.{table}", sql)
            self.assertIn(f"'{table}'", sql)  # in the loop that turns on row level security
        self.assertIn("owner_id = auth.uid()", sql)
        self.assertIn("create policy profiles_own", sql)
        self.assertIn("('scripts', 'scripts', false)", sql)  # a private bucket
        self.assertNotIn("service_role", sql.split("-- Row level security")[1].split("storage.buckets")[0].replace("grant", ""))


if __name__ == "__main__":
    unittest.main()
