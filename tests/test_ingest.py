"""Handwritten scripts: photos in, a PDF and checked transcripts out, marked like typed essays.

Run:  python -m unittest discover tests      Nothing here needs the internet or an API key: the Clerk's reads
come from the mock, which knows the sample pages in data/scripts by their hash.
"""
import base64
import hashlib
import json
import os
import re
import struct
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

os.environ["MOCK_DELAY"] = "0"
os.environ["MOCK"] = "1"  # never spend a real API key on tests

import run as server  # noqa: E402
from app import ingest, tools  # noqa: E402
from app.llm import Fallback, Gemini, LLMError, Mock, OpenRouter  # noqa: E402
from app.orchestrator import Run  # noqa: E402

DATA = Path(__file__).parent.parent / "data"
GOAL = "Mark the essays and send every learner feedback."


# ---- small builders ------------------------------------------------------------------------------

def make_png(width, height, colour, pixels, filters=(0,), palette=None):
    """A PNG built by hand. pixels: one bytes row per line (no filter byte). Rows cycle through `filters`."""
    bpp = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[colour]
    raw, prev = bytearray(), bytes(width * bpp)
    for y, row in enumerate(pixels):
        kind = filters[y % len(filters)]
        out = bytearray()
        for x, v in enumerate(row):
            a = row[x - bpp] if x >= bpp else 0
            b = prev[x]
            c = prev[x - bpp] if x >= bpp else 0
            if kind == 0:
                f = v
            elif kind == 1:
                f = v - a
            elif kind == 2:
                f = v - b
            elif kind == 3:
                f = v - ((a + b) >> 1)
            else:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                f = v - (a if pa <= pb and pa <= pc else b if pb <= pc else c)
            out.append(f & 0xFF)
        raw += bytes([kind]) + out
        prev = row

    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, colour, 0, 0, 0))
    if palette:
        png += chunk(b"PLTE", palette)
    return png + chunk(b"IDAT", zlib.compress(bytes(raw))) + chunk(b"IEND", b"")


def jpeg_with_orientation(orientation, width=40, height=20):
    """The markers of a JPEG with an EXIF orientation tag: enough for jpeg_info, not a picture."""
    tiff = b"MM\x00\x2a" + struct.pack(">I", 8) + struct.pack(">H", 1) + struct.pack(">HHI", 0x0112, 3, 1) \
        + struct.pack(">H", orientation) + b"\x00\x00" + struct.pack(">I", 0)
    app1 = b"Exif\x00\x00" + tiff
    sof = b"\x08" + struct.pack(">HH", height, width) + b"\x03" + b"\x01\x22\x00\x02\x11\x01\x03\x11\x01"
    return (b"\xff\xd8" + b"\xff\xe1" + struct.pack(">H", len(app1) + 2) + app1
            + b"\xff\xc0" + struct.pack(">H", len(sof) + 2) + sof + b"\xff\xda\x00\x02" + b"\xff\xd9")


def pdf_objects(data):
    """{object number: bytes of its body}, after checking every xref offset points at that object."""
    start = int(re.search(rb"startxref\n(\d+)\n%%EOF", data).group(1))
    table = data[start:]
    count = int(re.match(rb"xref\n0 (\d+)\n", table).group(1))
    rows = re.findall(rb"(\d{10}) 00000 n ", table)
    assert len(rows) == count - 1, "xref row count"
    objects = {}
    for n, offset in enumerate((int(r) for r in rows), 1):
        assert data[offset:].startswith(f"{n} 0 obj\n".encode()), f"object {n} is not at its xref offset"
        end = data.index(b"\nendobj\n", offset)
        objects[n] = data[offset + len(f"{n} 0 obj\n"):end]
    return objects


def sample_batch(root=None):
    root = root or tempfile.mkdtemp()
    batch = ingest.new_batch(root)
    ingest.add_pages(root, batch, ingest.sample_files(DATA))
    return root, batch


def run(goal=GOAL, llm=None, pages="sample", **kw):
    root, batch = sample_batch()
    chosen = ingest.load_pages(root, batch) if pages == "sample" else pages
    r = Run(llm or Mock(), goal, DATA, tempfile.mkdtemp(), pages=chosen, batch=batch, **kw)
    r._guarded()
    return r


def wait_for(condition, seconds=5):
    for _ in range(int(seconds * 20)):
        if condition():
            return True
        time.sleep(0.05)
    return False


class Scripted(Mock):
    """The mock, with chosen replies altered so awkward model behaviour can be rehearsed."""

    def __init__(self, **changes):
        super().__init__()
        self.changes, self.seen, self.data = changes, [], []

    def call(self, task, system, prompt, data=None, log=None):
        self.seen.append(task)
        self.data.append((task, data))
        reply = super().call(task, system, prompt, data, log)
        change = self.changes.get(task)
        return change(reply, data or {}) if change else reply


GOLDEN = {p["file"]: p for p in json.loads((DATA / "scripts" / "golden.json").read_text(encoding="utf-8"))["pages"]}


def on_page(files, change):
    """Alter the mock Clerk's reading of some sample pages. change(reply, attempt) returns the new reply."""
    shas = {GOLDEN[f]["sha256"] for f in ([files] if isinstance(files, str) else files)}
    return lambda reply, data: change(reply, data.get("attempt")) if data.get("sha256") in shas else reply


# ---- images and the PDF -----------------------------------------------------------------------------

class Images(unittest.TestCase):
    def test_only_jpeg_and_png_photos_are_taken(self):
        jpeg = (DATA / "scripts" / "ruan_botha_p1.jpg").read_bytes()
        self.assertEqual(ingest.check_image(jpeg), "image/jpeg")
        self.assertEqual(ingest.check_image(make_png(2, 1, 2, [bytes(6)])), "image/png")
        for bad, why in ((b"", "empty"), (b"GIF89a....", "not a JPEG or PNG"),
                         (b"\x00\x00\x00\x18ftypheic" + bytes(20), "HEIC"),
                         (b"\xff\xd8\xff\xd9", "no readable frame header")):
            with self.assertRaisesRegex(ingest.IngestError, why):
                ingest.check_image(bad, "photo.x")

    def test_jpeg_size_and_orientation_come_from_its_markers(self):
        self.assertEqual(ingest.jpeg_info((DATA / "scripts" / "sipho_ndlovu_p2.jpg").read_bytes()), (1000, 1414, 3, 1))
        for o in (1, 3, 6, 8):
            self.assertEqual(ingest.jpeg_info(jpeg_with_orientation(o))[3], o)
        # a photo taken holding the phone upright is stored sideways: it is shown turned, filling the page upright
        a, b, c, d, _, _ = (float(v) for v in ingest._placement(400, 200, 6).split())
        self.assertEqual((a, d), (0, 0))
        self.assertGreater(abs(b), abs(c))  # taller than wide once turned

    def test_png_rows_are_unfiltered_exactly(self):
        rows = [bytes((x * 37 + y * 11 + k * 5) & 0xFF for x in range(5) for k in range(4)) for y in range(5)]
        png = make_png(5, 5, 6, rows, filters=(0, 1, 2, 3, 4))
        info = ingest.png_info(png)
        self.assertEqual(bytes(ingest._unfilter(zlib.decompress(info["idat"]), 5, 5, 4)), b"".join(rows))

    def test_transparency_is_flattened_onto_white_paper(self):
        rows = [bytes([0, 0, 0, 255, 0, 0, 0, 0, 255, 0, 0, 128])]  # opaque black, see-through, half-see-through red
        keep, px = ingest._flatten_alpha(ingest.png_info(make_png(3, 1, 6, rows)))
        self.assertEqual(keep, 3)
        self.assertEqual(px[:6], bytes([0, 0, 0, 255, 255, 255]))
        self.assertEqual(px[6], 255)
        self.assertEqual(px[7], 127)

    def test_pdf_has_one_page_per_photo_in_order_and_a_sound_index(self):
        photos = [((DATA / "scripts" / f).read_bytes(), "image/jpeg") for f in ("ruan_botha_p2.jpg", "ruan_botha_p1.jpg")]
        photos += [(make_png(3, 2, 2, [bytes(range(9))] * 2), "image/png"),
                   (make_png(2, 2, 6, [bytes(8)] * 2, filters=(4,)), "image/png"),
                   (make_png(2, 1, 3, [bytes([0, 1])], palette=b"\xff\x00\x00\x00\x00\xff"), "image/png"),
                   (jpeg_with_orientation(6), "image/jpeg")]
        path = ingest.build_pdf(photos, Path(tempfile.mkdtemp()) / "out" / "scripts.pdf", "Test (scripts)")
        data = path.read_bytes()
        self.assertTrue(data.startswith(b"%PDF-1.4"))
        objects = pdf_objects(data)
        self.assertIn(b"/Count 6", objects[2])
        images = [body for body in objects.values() if b"/Subtype /Image" in body]
        self.assertEqual(len(images), 6)
        self.assertIn(photos[0][0], images[0])  # JPEGs go in untouched, and in the order given
        self.assertIn(b"/DCTDecode", images[1])
        self.assertIn(b"/Predictor 15", images[2])  # a plain PNG is decoded by the PDF reader, not here
        self.assertNotIn(b"/Predictor", images[3])  # transparency was flattened here
        self.assertIn(b"/Indexed /DeviceRGB 1 <ff00000000ff>", images[4])
        self.assertTrue(any(b"/Title (Test scripts)" in body for body in objects.values()))


class Uploads(unittest.TestCase):
    def test_multipart_bodies_are_read_byte_for_byte(self):
        payload = bytes(range(256)) * 3 + b"\r\n--not-the-boundary\r\n\r\n\n\r"
        body = (b"--XyZ\r\nContent-Disposition: form-data; name=\"batch\"\r\n\r\nabc123abc123\r\n"
                b"--XyZ\r\nContent-Disposition: form-data; name=\"pages\"; filename=\"p 1.jpg\"\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + payload + b"\r\n--XyZ--\r\n")
        parts = ingest.parse_multipart("multipart/form-data; boundary=XyZ", body)
        self.assertEqual([(p["name"], p["filename"]) for p in parts], [("batch", None), ("pages", "p 1.jpg")])
        self.assertEqual(parts[0]["data"], b"abc123abc123")
        self.assertEqual(parts[1]["data"], payload)
        with self.assertRaises(ingest.IngestError):
            ingest.parse_multipart("application/json", body)

    def test_a_batch_keeps_photos_in_the_order_the_teacher_chooses(self):
        root, batch = sample_batch()
        ids = [p["id"] for p in ingest.load_pages(root, batch)]
        self.assertEqual(ids, ["p01", "p02", "p03", "p04", "p05"])
        self.assertEqual([p["original"] for p in ingest.load_pages(root, batch)][0], "ruan_botha_p1.jpg")
        chosen = ingest.load_pages(root, batch, ["p02", "p01"])
        self.assertEqual([p["id"] for p in chosen], ["p02", "p01"])
        self.assertEqual(hashlib.sha256(chosen[0]["data"]).hexdigest(), chosen[0]["sha256"])
        for order, why in ((["p09"], "not in the batch"), (["p01", "p01"], "twice"), ([], "No pages")):
            with self.assertRaisesRegex(ingest.IngestError, why):
                ingest.load_pages(root, batch, order)

    def test_a_bad_photo_rejects_the_whole_upload(self):
        root, batch = sample_batch()
        good = make_png(2, 2, 2, [bytes(6)] * 2)
        with self.assertRaisesRegex(ingest.IngestError, "notes.txt is not a JPEG or PNG"):
            ingest.add_pages(root, batch, [("fine.png", good), ("notes.txt", b"hello")])
        self.assertEqual(len(ingest.load_pages(root, batch)), 5)  # nothing from the failed upload was kept
        pages = ingest.add_pages(root, batch, [("../../evil.png", good)])
        self.assertEqual((pages[-1]["id"], pages[-1]["original"]), ("p06", "evil.png"))
        with self.assertRaisesRegex(ingest.IngestError, "At most"):
            ingest.add_pages(root, batch, [("x.png", good)] * ingest.MAX_PAGES)

    def test_batch_and_page_names_cannot_reach_other_files(self):
        root, batch = sample_batch()
        for bad in ("../" + batch, "..", "", "ABCDEF123456", batch + "/.."):
            with self.assertRaises(ingest.IngestError):
                ingest.batch_folder(root, bad)
        for pid in ("../batch.json", "batch", "p1", ""):
            with self.assertRaises(ingest.IngestError):
                ingest.page_file(root, batch, pid)
        self.assertEqual(ingest.page_file(root, batch, "p01")[1], "image/jpeg")


# ---- the Clerk's checks, in code ---------------------------------------------------------------------

def read(**kw):
    base = {"name": "Ruan Botha", "page": 1, "of": 1, "lines": 3, "confidence": 0.9, "problem": "",
            "text": "One line of writing here\nand a second line here\nand a third line here"}
    return tools.clean_read({**base, **kw})


class ClerkChecks(unittest.TestCase):
    def setUp(self):
        self.subs = tools.load_submissions(DATA)

    def test_readings_are_tidied_whatever_the_model_sends(self):
        r = tools.clean_read({"name": "  Ruan   Botha ", "page": "2", "of": 2.0, "lines": "7", "confidence": 88,
                              "text": "a b [?]\r\nc  \n", "problem": "None."})
        self.assertEqual((r["name"], r["page"], r["of"], r["lines"], r["confidence"], r["problem"]), ("Ruan Botha", 2, 2, 7, 0.88, ""))
        self.assertEqual((r["text"], r["words"], r["unreadable"]), ("a b [?]\nc", 4, 1))
        for nonsense in (None, "text", [], {"confidence": "sure", "page": "one", "lines": None}, {"confidence": float("nan")}):
            r = tools.clean_read(nonsense)
            self.assertEqual((r["confidence"], r["page"], r["text"]), (0.0, None, ""))
            self.assertTrue(tools.check_read(r))

    def test_a_reading_is_checked_in_code(self):
        self.assertEqual(tools.check_read(read()), [])
        problems = lambda **kw: " | ".join(tools.check_read(read(**kw)))
        self.assertIn("only 60% sure", problems(confidence=0.6))
        self.assertIn("3 of its 15 words could not be read", problems(text="[?] [?] [?] one two three four five six seven\neight nine ten eleven twelve"))
        self.assertIn("has 3 lines but the page has 9 lines of writing, so some lines may have been skipped", problems(lines=9))
        self.assertIn("repeated or made up", problems(lines=1, text="a\nb\nc\nd\ne\nf"))
        self.assertEqual(problems(lines=5), "")  # two lines either way is allowed for
        self.assertIn("no text was read", problems(text=""))
        self.assertIn("reported a problem reading it (the photo is blurred)", problems(problem="The photo is blurred."))

    def test_names_must_be_on_the_class_list_exactly(self):
        self.assertEqual(tools.match_learner("sipho NDLOVU.", self.subs)["id"], "E02")
        self.assertIsNone(tools.match_learner("Sipho Ndlovo", self.subs))
        self.assertIsNone(tools.match_learner("", self.subs))
        self.assertEqual(tools.close_learners("Sipho Ndlovo", self.subs), [{"id": "E02", "learner": "Sipho Ndlovu"}])
        self.assertEqual([c["id"] for c in tools.close_learners("R. Botha", self.subs)], ["E08"])  # same surname
        self.assertEqual(tools.close_learners("Mary Smith", self.subs), [])

    def test_pages_are_sorted_into_scripts(self):
        pages = [
            {"id": "a", "read": read(name="Ruan Botha", page=2, of=2)},
            {"id": "b", "read": read(name="Sipho Ndlovu", page=1, of=2)},
            {"id": "c", "read": read(name="", page=2, of=2)},  # continues Sipho's script
            {"id": "d", "read": read(name="ruan botha", page=1, of=2)},  # Ruan's first page, photographed last
            {"id": "e", "read": read(name="", page=2, of=2)},  # Ruan already has a page 2: a script of its own
        ]
        scripts = tools.group_pages(pages)
        self.assertEqual([(s["name"], s["pages"], s["reordered"]) for s in scripts],
                         [("Ruan Botha", ["d", "a"], True), ("Sipho Ndlovu", ["b", "c"], False), ("", ["e"], False)])
        reads = {p["id"]: p["read"] for p in pages}
        self.assertEqual(tools.check_script(scripts[0], reads, self.subs), (self.subs[7], []))
        learner, problems = tools.check_script(scripts[2], reads, self.subs)
        self.assertIsNone(learner)
        self.assertEqual(problems, ["no learner's name can be read on any of its pages", "page 1 of 2 is missing"])

    def test_page_numbers_must_add_up(self):
        def problems(*numbers):
            pages = [{"id": f"x{i}", "read": read(page=n, of=o)} for i, (n, o) in enumerate(numbers)]
            script = tools.group_pages(pages)[0]
            return tools.check_script(script, {p["id"]: p["read"] for p in pages}, self.subs)[1]
        self.assertEqual(problems((1, 2), (2, 2)), [])
        self.assertEqual(problems((1, 2)), ["page 2 of 2 is missing"])
        self.assertEqual(problems((1, 2), (1, 2)), ["page 1 appears 2 times", "page 2 of 2 is missing"])
        self.assertIn("its pages disagree on how many pages there are (of 2, of 3)", problems((1, 2), (2, 3)))
        self.assertIn("page 3 is numbered beyond the 2 pages it says there are", problems((1, 2), (2, 2), (3, 2)))
        self.assertIn("1 of its pages carries no page number", problems((1, 2), (2, 2), (None, None)))
        self.assertEqual(problems((None, None)), [])  # a single page with no number is fine

    def test_transcripts_read_like_typed_essays(self):
        self.assertEqual(tools.script_text(["Title\n\nOne line\nwraps here.\n\nNext", "Page two\nends."]),
                         "Title\n\nOne line wraps here.\n\nNext\n\nPage two ends.")


# ---- the workflow ----------------------------------------------------------------------------------

class Workflow(unittest.TestCase):
    def test_sample_scripts_are_read_checked_and_marked_like_typed_essays(self):
        llm = Scripted()
        r = run(llm=llm)
        typed = Run(Mock(), GOAL, DATA, tempfile.mkdtemp())
        typed._guarded()
        self.assertEqual(r.status, "done")
        self.assertEqual(list(r.agent_state), ["PL", "CL", "MK", "RV", "MS", "CO", "DS"])
        self.assertEqual((r.agent_state["CL"], r.agent_state["CO"]), ("done", "off"))
        self.assertEqual(llm.seen[:2], ["intake", "read_page"])  # the Planner decides first, then the Clerk reads
        self.assertEqual(llm.seen.count("read_page"), 5 + 2)  # every page once; Sipho's misread name and Bongani's page again

        scripts = {s["id"]: s for s in r.intake["scripts"]}
        self.assertEqual({k: (s["learner"], s["status"]) for k, s in scripts.items()},
                         {"S1": ("E08", "accepted"), "S2": ("E02", "accepted"), "S3": ("E10", "held")})
        self.assertEqual(scripts["S3"]["problems"], ["page 2 of 2 is missing"])
        pages = {p["id"]: p for p in r.intake["pages"]}
        self.assertEqual((pages["p03"]["reads"], pages["p03"]["first"]["name"], pages["p03"]["read"]["name"]), (2, "Sipho Ndlovo", "Sipho Ndlovu"))
        self.assertEqual(pages["p03"]["first_problems"], ["the name “Sipho Ndlovo” is not on the class list"])
        self.assertIn("read_page", [t for t, d in llm.data if d and d.get("attempt") == 2])

        by = {s["id"]: s for s in r.subs}
        self.assertEqual((by["E08"]["status"], by["E08"]["source"]), ("delivered", "script"))  # his full essay was on paper
        self.assertEqual({s["id"]: s["status"] for s in typed.subs}["E08"], "resubmit")
        self.assertEqual(by["E02"]["final"]["total"], {s["id"]: s for s in typed.subs}["E02"]["final"]["total"])
        self.assertEqual(by["E02"]["text"], {s["id"]: s for s in typed.subs}["E02"]["text"].replace("\r\n", "\n"))
        self.assertEqual((by["E10"]["status"], by["E10"]["script_hold"], by["E10"]["final"]), ("escalated", True, None))
        self.assertIn("page 2 of 2 is missing", by["E10"]["issue"])
        self.assertEqual((r.stats["escalated"], r.stats["delivered"]), (1, 11))
        self.assertTrue(any(e["agent"] == "CL" and e["kind"] == "REJECT" and "Sipho Ndlovu" in e["msg"] for e in r.events))
        self.assertTrue(any(e["agent"] == "CL" and e["kind"] == "FIX" and "name now “Sipho Ndlovu”" in e["msg"] for e in r.events))
        self.assertTrue(r.events[-1]["msg"].startswith("5 photographed pages read as 3 handwritten scripts: 2 accepted, 1 held"))

        # real artefacts, in output/<run>/scripts
        out = r.out_dir / "scripts"
        self.assertEqual(r.files[:5], ["scripts/all_pages.pdf", "scripts/E08_Ruan_Botha.pdf", "scripts/E02_Sipho_Ndlovu.pdf",
                                       "scripts/E10_Bongani_Sithole.pdf", "scripts/clerk_report.md"])
        self.assertIn(b"/Count 5", pdf_objects((out / "all_pages.pdf").read_bytes())[2])
        self.assertIn(b"/Count 2", pdf_objects((out / "E08_Ruan_Botha.pdf").read_bytes())[2])
        self.assertEqual(len(list((out / "pages").glob("*.jpg"))), 5)
        self.assertIn("Firstly, technology helps us with school.", (out / "transcripts" / "E08_Ruan_Botha.txt").read_text(encoding="utf-8"))
        report = (out / "clerk_report.md").read_text(encoding="utf-8")
        self.assertIn("### S3: E10 Bongani Sithole", report)
        self.assertIn("yes: the name “Sipho Ndlovo” is not on the class list", report)
        self.assertIn("## Handwritten scripts", (r.out_dir / "class_report.md").read_text(encoding="utf-8"))
        self.assertIn("the handwritten script needs your check", next(a["why"] for a in r.report["attention"] if a["id"] == "E10"))
        json.dumps(r.snapshot())  # the dashboard reads all of it, so there must be no photo bytes in it

    def test_injected_ocr_fault_is_caught_by_the_line_count_and_fixed(self):
        clean = run()
        r = run(inject_ocr_fault=True)
        p01 = next(p for p in r.intake["pages"] if p["id"] == "p01")
        self.assertEqual(p01["reads"], 2)
        self.assertEqual(p01["first_problems"], ["the transcript has 6 lines but the page has 13 lines of writing, so some lines may have been skipped"])
        self.assertEqual(tools.written_lines(p01["read"]["text"]), 13)
        self.assertEqual(r.intake["scripts"][0]["status"], "accepted")
        self.assertEqual(r._sub("E08")["text"], clean._sub("E08")["text"])  # nothing of the fault reached the marker
        self.assertEqual(r._sub("E08")["final"], clean._sub("E08")["final"])
        self.assertTrue(any(e["kind"] == "TEST" and "p01" in e["msg"] for e in r.events))
        self.assertEqual(r.stats["sent_back"], 0)  # the marking fault is a separate switch

    def test_the_planner_can_decide_the_photos_are_not_needed(self):
        llm = Scripted()
        r = run("Mark only the typed essays and send feedback. Ignore the photos.", llm=llm)
        self.assertEqual((r.status, r.agent_state["CL"], r.intake), ("done", "off", None))
        self.assertNotIn("read_page", llm.seen)
        self.assertTrue(any(e["kind"] == "DECIDE" and "will not be read" in e["msg"] for e in r.events))
        self.assertEqual(r._sub("E08")["status"], "resubmit")
        self.assertFalse((r.out_dir / "scripts").exists())

    def test_essay_only_runs_have_no_clerk(self):
        llm = Scripted()
        r = Run(llm, GOAL, DATA, tempfile.mkdtemp())
        r._guarded()
        self.assertNotIn("CL", r.agent_state)
        self.assertFalse({"intake", "read_page"} & set(llm.seen))
        self.assertIsNone(r.snapshot()["scripts"])

    def test_teacher_accepts_a_held_script_and_it_is_marked_and_delivered(self):
        r = run()
        s = r._sub("E10")
        self.assertFalse(r.resolve("E10", "marker"))  # there is no mark to choose: it is the script that is held
        self.assertFalse(r.resolve_script("S3", "accept", "E01"))  # Bongani's script cannot be given to someone else
        self.assertTrue(r.resolve_script("S3", "accept"))
        self.assertTrue(wait_for(lambda: s["status"] == "delivered"))
        self.assertEqual((s["source"], s["script_hold"], s["issue"]), ("script", False, None))
        self.assertEqual((r.stats["escalated"], r.stats["human_interventions"], r.stats["delivered"]), (0, 1, 12))
        self.assertTrue(any(h["who"] == "Teacher" for h in s["history"]))
        self.assertTrue(any(e["kind"] == "ACT" and e["msg"].startswith("Released by the teacher: marking E10") for e in r.events))
        self.assertEqual(len(list((r.out_dir / "outbox").glob("E10*"))), 1)
        self.assertTrue(wait_for(lambda: "Decided by the teacher" in (r.out_dir / "scripts" / "clerk_report.md").read_text(encoding="utf-8")))
        self.assertFalse(r.resolve_script("S3", "accept"))  # already settled

    def test_teacher_sets_a_held_script_aside(self):
        r = run()
        s = r._sub("E10")
        self.assertTrue(r.resolve_script("S3", "set_aside"))
        self.assertTrue(wait_for(lambda: bool(s["feedback"])))
        self.assertEqual((s["status"], s["final"]), ("resubmit", None))
        self.assertIn("incomplete", s["feedback"]["body"])
        self.assertEqual((r.stats["escalated"], r.stats["resubmit"], r.stats["human_interventions"]), (0, 1, 1))
        self.assertEqual(next(x for x in r.intake["scripts"] if x["id"] == "S3")["status"], "set_aside")
        self.assertFalse(r.resolve_script("S3", "set_aside"))
        self.assertFalse(r.resolve_script("S9", "accept"))
        self.assertFalse(r.resolve_script("S1", "keep"))

    def test_a_name_still_not_on_the_list_is_held_until_the_teacher_says_whose_it_is(self):
        initial = on_page(["ruan_botha_p1.jpg", "ruan_botha_p2.jpg"], lambda reply, attempt: {**reply, "name": "R. Botha"})
        r = run(llm=Scripted(read_page=initial))
        rec = r.intake["scripts"][0]
        self.assertEqual((rec["learner"], rec["status"], rec["name"]), (None, "held", "R. Botha"))
        self.assertEqual(rec["problems"][0], "the name “R. Botha” is not on the class list")
        self.assertEqual(rec["suggest"], [{"id": "E08", "learner": "Ruan Botha"}])
        self.assertEqual(r._sub("E08")["status"], "resubmit")  # his typed essay is too short, and the script is nobody's yet
        self.assertIn(rec["id"], {a["id"] for a in r.report["attention"]})
        self.assertFalse(r.resolve_script(rec["id"], "accept"))  # whose is it?
        self.assertFalse(r.resolve_script(rec["id"], "accept", "E01"))  # Thandi's essay is already marked
        self.assertTrue(r.resolve_script(rec["id"], "accept", "E08"))
        self.assertTrue(wait_for(lambda: r._sub("E08")["status"] == "delivered"))
        self.assertEqual((r._sub("E08")["source"], r.stats["resubmit"]), ("script", 0))
        self.assertNotIn("resubmit", r._sub("E08")["feedback"]["subject"].lower())

    def test_a_writer_not_on_the_list_can_be_added_and_their_script_marked(self):
        stranger = on_page(["ruan_botha_p1.jpg", "ruan_botha_p2.jpg"], lambda reply, attempt: {**reply, "name": "Musa Khoza"})
        r = run(llm=Scripted(read_page=stranger))
        rec = r.intake["scripts"][0]
        self.assertEqual((rec["status"], rec["learner"]), ("held", None))
        self.assertFalse(r.resolve_script(rec["id"], "add", name="Ruan Botha"))  # already on the class list
        self.assertFalse(r.resolve_script(rec["id"], "add", email="not an address"))
        self.assertTrue(r.resolve_script(rec["id"], "add", email="musa.khoza@example.com"))
        s = r._sub("E13")  # the next id in the class list's own style
        self.assertEqual((s["learner"], s["email"], s["added"], s["source"]), ("Musa Khoza", "musa.khoza@example.com", True, "script"))
        self.assertEqual((rec["status"], rec["learner"], rec["decided"]), ("accepted", "E13", "teacher"))
        self.assertTrue(wait_for(lambda: s["status"] == "delivered"))
        self.assertEqual(r.stats["human_interventions"], 1)
        self.assertTrue(any(e["kind"] == "HUMAN" and "added Musa Khoza" in e["msg"] for e in r.events))
        self.assertFalse(r.resolve_script(rec["id"], "add"))  # already settled

    def test_a_writer_not_on_the_list_can_be_blocked(self):
        stranger = on_page(["ruan_botha_p1.jpg", "ruan_botha_p2.jpg"], lambda reply, attempt: {**reply, "name": "Musa Khoza"})
        r = run(llm=Scripted(read_page=stranger))
        rec, before = r.intake["scripts"][0], len(r.subs)
        self.assertTrue(r.resolve_script(rec["id"], "set_aside"))
        self.assertEqual((rec["status"], len(r.subs)), ("set_aside", before))
        self.assertTrue(any(e["kind"] == "HUMAN" and "blocked handwritten script" in e["msg"].lower() for e in r.events))

    def test_a_reread_that_swaps_in_a_different_name_is_not_trusted(self):
        swap = on_page("sipho_ndlovu_p1.jpg", lambda reply, attempt: {**reply, "name": "Lerato Khumalo"} if attempt == 2 else reply)
        r = run(llm=Scripted(read_page=swap))
        held = [x for x in r.intake["scripts"] if x["status"] == "held"]
        self.assertTrue(any("too big a change to be a correction" in " ".join(x["problems"]) for x in held))
        self.assertEqual(r._sub("E03")["source"], "typed")  # Lerato's own essay was not replaced by a guess
        self.assertEqual(r.status, "done")

    def test_a_photo_the_model_cannot_read_is_held_and_the_run_carries_on(self):
        def fails(reply, data):
            if data.get("sha256") == GOLDEN["bongani_sithole_p1.jpg"]["sha256"]:
                raise LLMError("Gemini HTTP 400: image could not be processed")
            return reply
        llm = Scripted(read_page=fails)
        r = run(llm=llm)
        self.assertEqual(r.status, "done")
        rec = next(x for x in r.intake["scripts"] if "p05" in x["pages"])
        self.assertEqual((rec["status"], rec["learner"], rec["words"]), ("held", None, 0))
        self.assertIn("image could not be processed", " ".join(rec["problems"]))
        self.assertFalse(r.resolve_script(rec["id"], "accept", "E08"))  # an empty transcript cannot be marked
        self.assertTrue(r.resolve_script(rec["id"], "set_aside"))
        self.assertEqual(r._sub("E10")["source"], "typed")  # without a readable script, Bongani's typed essay stands

    def test_an_unknown_photo_in_offline_mode_says_why_it_was_not_read(self):
        root = tempfile.mkdtemp()
        batch = ingest.new_batch(root)
        ingest.add_pages(root, batch, [("mine.png", make_png(4, 4, 0, [bytes(4)] * 4))])
        r = Run(Mock(), GOAL, DATA, tempfile.mkdtemp(), pages=ingest.load_pages(root, batch), batch=batch)
        r._guarded()
        self.assertEqual(r.status, "done")
        self.assertIn("offline demo mode can only read the sample scripts", " ".join(r.intake["scripts"][0]["problems"]))
        self.assertEqual(r.stats["delivered"], 11)  # the typed essays were marked as usual


# ---- the model clients, with photos -----------------------------------------------------------------

class FakeAPI(BaseHTTPRequestHandler):
    seen, reply = [], {}

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeAPI.seen.append(body)
        data = json.dumps(FakeAPI.reply).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class VisionClients(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), FakeAPI)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def setUp(self):
        FakeAPI.seen = []
        self.photo = [{"mime": "image/jpeg", "data": b"\xff\xd8\xff photo bytes"}]

    def test_gemini_sends_the_photo_as_inline_data(self):
        FakeAPI.reply = {"candidates": [{"content": {"parts": [{"text": '{"text": "read"}'}]}}]}
        os.environ["GEMINI_API_BASE"] = self.base + "/v1beta"
        try:
            g = Gemini("k")
            g.min_gap = 0
            self.assertEqual(g.call_vision("read_page", "You are the Clerk.", "Transcribe.", self.photo), {"text": "read"})
        finally:
            del os.environ["GEMINI_API_BASE"]
        parts = FakeAPI.seen[0]["contents"][0]["parts"]
        self.assertEqual(parts[0], {"text": "Transcribe."})
        self.assertEqual(parts[1]["inline_data"]["mime_type"], "image/jpeg")
        self.assertEqual(base64.b64decode(parts[1]["inline_data"]["data"]), self.photo[0]["data"])

    def test_openrouter_sends_the_photo_as_an_image_url_to_the_vision_model(self):
        FakeAPI.reply = {"model": "v/vision:free", "choices": [{"message": {"content": '{"text": "read"}'}}]}
        os.environ["OPENROUTER_API_BASE"] = self.base + "/api/v1"
        os.environ["OPENROUTER_VISION_MODEL"] = "v/vision:free"
        try:
            o = OpenRouter("k")
            o.min_gap = 0
            self.assertEqual(o.call_vision("read_page", "You are the Clerk.", "Transcribe.", self.photo), {"text": "read"})
            o.call("mark", "s", "p")
        finally:
            del os.environ["OPENROUTER_API_BASE"], os.environ["OPENROUTER_VISION_MODEL"]
        vision, text = FakeAPI.seen
        self.assertEqual(vision["model"], "v/vision:free")
        content = vision["messages"][1]["content"]
        self.assertEqual(content[0], {"type": "text", "text": "Transcribe."})
        self.assertTrue(content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,"))
        self.assertEqual((text["model"], text["messages"][1]["content"]), ("openrouter/free", "p"))  # text calls are unchanged

    def test_fallback_and_mock_both_take_photos(self):
        class Refuses(Gemini):
            def call_vision(self, *a, **k):
                raise LLMError("Gemini refused the API key")

        class Backup(Mock):
            name, model = "openrouter", "openrouter/free"

        llm = Fallback(Refuses("k"), Backup())
        page = GOLDEN["ruan_botha_p2.jpg"]
        reply = llm.call_vision("read_page", "s", "p", self.photo, {"sha256": page["sha256"], "attempt": 1})
        self.assertEqual((reply["name"], llm.name), ("Ruan Botha", "openrouter"))


# ---- the web server ---------------------------------------------------------------------------------

class WebApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        server.OUTPUT = Path(tempfile.mkdtemp())
        server.current["run"] = None
        cls.httpd = server.Server(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def request(self, path, body=None, headers=None):
        data = json.dumps(body).encode() if isinstance(body, dict) else body
        req = urllib.request.Request(self.base + path, data=data, headers=headers or {"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.status, r.headers, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read()

    def upload(self, files, batch=None):
        parts = [(b'Content-Disposition: form-data; name="batch"\r\n\r\n' + batch.encode())] if batch else []
        parts += [f'Content-Disposition: form-data; name="pages"; filename="{name}"\r\nContent-Type: image/png\r\n\r\n'.encode() + data
                  for name, data in files]
        body = b"".join(b"--B0undary\r\n" + p + b"\r\n" for p in parts) + b"--B0undary--\r\n"
        code, _, out = self.request("/api/ingest", body, {"Content-Type": "multipart/form-data; boundary=B0undary"})
        return code, json.loads(out)

    def test_photos_in_marked_work_out(self):
        code, _, out = self.request("/api/ingest?sample=1", b"")
        self.assertEqual(code, 200)
        staged = json.loads(out)
        batch = staged["batch"]
        self.assertEqual([p["original"] for p in staged["pages"]][:2], ["ruan_botha_p1.jpg", "ruan_botha_p2.jpg"])
        code, headers, photo = self.request(f"/api/page?batch={batch}&id=p01")
        self.assertEqual((code, headers["Content-Type"], photo[:3]), (200, "image/jpeg", b"\xff\xd8\xff"))
        self.assertEqual(self.request(f"/api/page?batch={batch}&id=p99")[0], 404)
        self.assertEqual(self.request("/api/page?batch=..&id=p01")[0], 404)

        self.assertEqual(self.upload([("notes.png", b"not a photo")], batch)[0], 400)
        code, extra = self.upload([("extra.png", make_png(2, 2, 2, [bytes(6)] * 2))], batch)
        self.assertEqual((code, extra["batch"], len(extra["pages"])), (200, batch, 6))
        self.assertEqual(self.upload([])[0], 400)

        bad = {"goal": GOAL, "scripts": {"batch": batch, "order": ["p01", "p77"]}}
        self.assertEqual(self.request("/api/run", bad)[0], 400)
        order = ["p01", "p02", "p03", "p04", "p05"]  # the teacher left the extra photo out
        body = {"goal": GOAL, "inject_ocr_fault": True, "scripts": {"batch": batch, "order": order}}
        self.assertEqual(self.request("/api/run", body)[0], 200)
        state = lambda: json.loads(self.request("/api/state?since=999999")[2])
        self.assertTrue(wait_for(lambda: state()["status"] == "done", 30))
        done = state()
        self.assertEqual(done["agents"]["CL"], "done")
        self.assertTrue(done["inject_ocr_fault"])
        self.assertEqual([p["id"] for p in done["scripts"]["pages"]], order)
        self.assertEqual(done["scripts"]["batch"], batch)

        code, headers, pdf = self.request("/api/file?name=scripts/all_pages.pdf")
        self.assertEqual((code, headers["Content-Type"], pdf[:5]), (200, "application/pdf", b"%PDF-"))
        self.assertIn('filename="all_pages.pdf"', headers["Content-Disposition"])
        code, headers, report = self.request("/api/file?name=scripts/clerk_report.md")
        self.assertEqual((code, headers["Content-Type"]), (200, "text/markdown; charset=utf-8"))
        self.assertIn("p01", report.decode("utf-8"))
        self.assertEqual(self.request("/api/file?name=scripts/pages")[0], 404)

        decision = {"kind": "script", "id": "S3", "choice": "accept"}
        self.assertEqual(self.request("/api/resolve", decision)[0], 200)
        self.assertEqual(self.request("/api/resolve", decision)[0], 400)
        self.assertTrue(wait_for(lambda: next(s for s in state()["subs"] if s["id"] == "E10")["status"] == "delivered", 10))


if __name__ == "__main__":
    unittest.main()
