"""Photos of handwritten scripts: checking uploads, keeping them until a run reads them, and binding them into a PDF.

Standard library only. JPEG photos go into the PDF as they are; PNG images go in through the PDF's own PNG
decoder, and are only decoded here when they carry transparency that has to be flattened onto white paper.
"""
import hashlib
import json
import re
import secrets
import shutil
import struct
import zlib
from pathlib import Path

MAX_PAGES = 40
MAX_BYTES = 15 * 1024 * 1024  # one photo
MAX_UPLOAD = 80 * 1024 * 1024  # one request
BATCH_ID = re.compile(r"^[0-9a-f]{12}$")
PAGE_ID = re.compile(r"^p\d{2,3}$")
A4 = (595.0, 842.0)  # points
MARGIN = 18.0


class IngestError(ValueError):
    """An upload that cannot be used, with a reason a teacher can act on."""


# ---- what kind of image is this? ------------------------------------------------------------

def sniff(data):
    """The image type from the file's first bytes, never from its name: 'image/jpeg', 'image/png' or None."""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    return None


def _exif_orientation(segment):
    """The EXIF orientation (1-8) inside an APP1 segment's payload, or 1."""
    if segment[:6] != b"Exif\x00\x00":
        return 1
    tiff = segment[6:]
    if len(tiff) < 8 or tiff[:2] not in (b"II", b"MM"):
        return 1
    end = "<" if tiff[:2] == b"II" else ">"
    try:
        (ifd,) = struct.unpack(end + "I", tiff[4:8])
        (count,) = struct.unpack(end + "H", tiff[ifd:ifd + 2])
        for i in range(count):
            at = ifd + 2 + 12 * i
            tag, kind = struct.unpack(end + "HH", tiff[at:at + 4])
            if tag == 0x0112 and kind == 3:
                (value,) = struct.unpack(end + "H", tiff[at + 8:at + 10])
                return value if 1 <= value <= 8 else 1
    except struct.error:
        return 1
    return 1


def jpeg_info(data):
    """(width, height, colour components, EXIF orientation) of a JPEG, read from its markers."""
    i, orientation = 2, 1
    sof = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
    while i + 4 <= len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker == 0xFF:  # fill byte
            i += 1
            continue
        if marker in (0x01, 0xD8) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        if marker in (0xD9, 0xDA):  # end of image, or the image data begins: no frame header was found
            break
        (length,) = struct.unpack(">H", data[i + 2:i + 4])
        payload = data[i + 4:i + 2 + length]
        if marker == 0xE1 and orientation == 1:
            orientation = _exif_orientation(payload)
        if marker in sof and len(payload) >= 6:
            height, width = struct.unpack(">HH", payload[1:5])
            if width and height:
                return width, height, payload[5], orientation
        i += 2 + length
    raise IngestError("The JPEG has no readable frame header, so it may be damaged.")


def _png_chunks(data):
    i = 8
    while i + 8 <= len(data):
        (length,) = struct.unpack(">I", data[i:i + 4])
        kind = data[i + 4:i + 8]
        yield kind, data[i + 8:i + 8 + length]
        i += 12 + length
        if kind == b"IEND":
            return


def png_info(data):
    """The PNG's header and image data: {width, height, depth, colour, interlace, palette, idat}."""
    info = {"palette": b"", "idat": b""}
    idat = []
    for kind, body in _png_chunks(data):
        if kind == b"IHDR" and len(body) >= 13:
            w, h, depth, colour, _, _, interlace = struct.unpack(">IIBBBBB", body[:13])
            info.update(width=w, height=h, depth=depth, colour=colour, interlace=interlace)
        elif kind == b"PLTE":
            info["palette"] = body
        elif kind == b"IDAT":
            idat.append(body)
    if "width" not in info or not idat:
        raise IngestError("The PNG is incomplete, so it may be damaged.")
    info["idat"] = b"".join(idat)
    return info


def _unfilter(raw, width, height, bpp):
    """Undo PNG row filters. Returns the image bytes without the filter-type byte that starts each row."""
    stride = width * bpp
    out = bytearray(stride * height)
    prev = bytearray(stride)
    at = 0
    for y in range(height):
        kind = raw[at]
        row = bytearray(raw[at + 1:at + 1 + stride])
        at += 1 + stride
        if kind == 1:
            for x in range(bpp, stride):
                row[x] = (row[x] + row[x - bpp]) & 0xFF
        elif kind == 2:
            for x in range(stride):
                row[x] = (row[x] + prev[x]) & 0xFF
        elif kind == 3:
            for x in range(stride):
                left = row[x - bpp] if x >= bpp else 0
                row[x] = (row[x] + ((left + prev[x]) >> 1)) & 0xFF
        elif kind == 4:
            for x in range(stride):
                a = row[x - bpp] if x >= bpp else 0
                b = prev[x]
                c = prev[x - bpp] if x >= bpp else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                row[x] = (row[x] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 0xFF
        elif kind != 0:
            raise IngestError("The PNG uses an unknown row filter, so it may be damaged.")
        out[y * stride:(y + 1) * stride] = row
        prev = row
    return out


def _flatten_alpha(info):
    """A PNG with transparency (grey+alpha or RGBA, 8 bits) as plain pixels on white: (colours, pixel bytes)."""
    w, h, colour = info["width"], info["height"], info["colour"]
    channels = 2 if colour == 4 else 4
    px = _unfilter(zlib.decompress(info["idat"]), w, h, channels)
    keep = channels - 1
    out = bytearray(w * h * keep)
    j = 0
    for i in range(0, len(px), channels):
        alpha = px[i + keep]
        for k in range(keep):
            out[j + k] = (px[i + k] * alpha + 255 * (255 - alpha)) // 255
        j += keep
    return keep, bytes(out)


def check_image(data, name="the file"):
    """The image type of an upload, or IngestError saying why it cannot be used."""
    if not data:
        raise IngestError(f"{name} is empty.")
    if len(data) > MAX_BYTES:
        raise IngestError(f"{name} is larger than {MAX_BYTES // (1024 * 1024)} MB. Take the photo at a lower resolution.")
    mime = sniff(data)
    if not mime:
        raise IngestError(f"{name} is not a JPEG or PNG photo. Phones that save HEIC can share or export the photo as JPEG.")
    if mime == "image/jpeg":
        jpeg_info(data)
    else:
        info = png_info(data)
        if info["interlace"]:
            raise IngestError(f"{name} is an interlaced PNG. Save it again without interlacing, or as a JPEG.")
        if info["depth"] != 8 and not (info["colour"] in (0, 3) and info["depth"] in (1, 2, 4)):
            raise IngestError(f"{name} uses {info['depth']}-bit colour. Save it again as an ordinary 8-bit PNG or a JPEG.")
    return mime


# ---- the PDF -----------------------------------------------------------------------------------

def _image_object(data, mime):
    """(PDF image dictionary entries, stream bytes, width, height, EXIF orientation) for one page image."""
    if mime == "image/jpeg":
        w, h, comps, orientation = jpeg_info(data)
        space = {1: "/DeviceGray", 3: "/DeviceRGB", 4: "/DeviceCMYK"}.get(comps, "/DeviceRGB")
        return f"/ColorSpace {space} /BitsPerComponent 8 /Filter /DCTDecode", data, w, h, orientation
    info = png_info(data)
    w, h, colour, depth = info["width"], info["height"], info["colour"], info["depth"]
    if colour in (4, 6):
        keep, px = _flatten_alpha(info)
        space = "/DeviceGray" if keep == 1 else "/DeviceRGB"
        return f"/ColorSpace {space} /BitsPerComponent 8 /Filter /FlateDecode", zlib.compress(px), w, h, 1
    colours = {0: 1, 2: 3, 3: 1}[colour]
    if colour == 3:
        pal = info["palette"]
        space = f"[/Indexed /DeviceRGB {len(pal) // 3 - 1} <{pal.hex()}>]"
    else:
        space = "/DeviceGray" if colour == 0 else "/DeviceRGB"
    parms = f"/DecodeParms << /Predictor 15 /Colors {colours} /BitsPerComponent {depth} /Columns {w} >>"
    return f"/ColorSpace {space} /BitsPerComponent {depth} /Filter /FlateDecode {parms}", info["idat"], w, h, 1


def _placement(w, h, orientation):
    """The content-stream matrix that fits an image onto an A4 page, turned the way its EXIF tag says."""
    turned = orientation in (5, 6, 7, 8)
    shown_w, shown_h = (h, w) if turned else (w, h)
    scale = min((A4[0] - 2 * MARGIN) / shown_w, (A4[1] - 2 * MARGIN) / shown_h)
    bw, bh = shown_w * scale, shown_h * scale
    x, y = (A4[0] - bw) / 2, (A4[1] - bh) / 2
    if orientation == 6:  # shown turned a quarter clockwise
        m = (0, -bh, bw, 0, x, y + bh)
    elif orientation == 8:  # a quarter anticlockwise
        m = (0, bh, -bw, 0, x + bw, y)
    elif orientation == 3:  # upside down
        m = (-bw, 0, 0, -bh, x + bw, y + bh)
    else:
        m = (bw, 0, 0, bh, x, y)
    return " ".join(f"{v:.2f}" for v in m)


def build_pdf(images, path, title="Scripts"):
    """Write one A4 page per image, in the order given. images: [(bytes, mime)]. Returns the path."""
    objects = []  # bytes of each object body, numbered from 1

    def add(body):
        objects.append(body)
        return len(objects)

    catalog = add(b"")  # filled in once the page tree exists
    tree = add(b"")
    kids = []
    for n, (data, mime) in enumerate(images, 1):
        entries, stream, w, h, orientation = _image_object(data, mime)
        image = add(f"<< /Type /XObject /Subtype /Image /Width {w} /Height {h} {entries} /Length {len(stream)} >>\nstream\n".encode()
                    + stream + b"\nendstream")
        draw = f"q {_placement(w, h, orientation)} cm /Im{n} Do Q".encode()
        content = add(f"<< /Length {len(draw)} >>\nstream\n".encode() + draw + b"\nendstream")
        kids.append(add(f"<< /Type /Page /Parent {tree} 0 R /MediaBox [0 0 {A4[0]:.0f} {A4[1]:.0f}] "
                        f"/Resources << /XObject << /Im{n} {image} 0 R >> >> /Contents {content} 0 R >>".encode()))
    objects[tree - 1] = f"<< /Type /Pages /Kids [{' '.join(f'{k} 0 R' for k in kids)}] /Count {len(kids)} >>".encode()
    objects[catalog - 1] = f"<< /Type /Catalog /Pages {tree} 0 R >>".encode()
    safe_title = re.sub(r"[()\\]", "", title)
    info = add(f"<< /Title ({safe_title}) /Producer (Marking Colleague) >>".encode())

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root {catalog} 0 R /Info {info} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(out))
    return path


# ---- uploads -----------------------------------------------------------------------------------

def parse_multipart(content_type, body):
    """The parts of a multipart/form-data body: [{name, filename, data}]. Standard library only, and binary-safe."""
    m = re.search(r'boundary="?([^";]+)"?', content_type or "", re.I)
    if not m or "multipart/form-data" not in (content_type or "").lower():
        raise IngestError("Send the photos as multipart/form-data.")
    boundary = b"--" + m.group(1).encode()
    parts = []
    for chunk in body.split(boundary)[1:]:
        if chunk.startswith(b"--"):  # the closing boundary
            break
        chunk = chunk[2:] if chunk.startswith(b"\r\n") else chunk
        head, sep, data = chunk.partition(b"\r\n\r\n")
        if not sep:
            continue
        if data.endswith(b"\r\n"):
            data = data[:-2]
        headers = head.decode("utf-8", "replace")
        disposition = next((line for line in headers.split("\r\n") if line.lower().startswith("content-disposition")), "")
        name = re.search(r'\bname="([^"]*)"', disposition)
        filename = re.search(r'\bfilename="([^"]*)"', disposition)
        parts.append({"name": name.group(1) if name else "", "filename": filename.group(1) if filename else None, "data": data})
    return parts


def _manifest(folder):
    path = Path(folder) / "batch.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def _save_manifest(folder, pages):
    (Path(folder) / "batch.json").write_text(json.dumps(pages, indent=1), encoding="utf-8")


def batch_folder(root, batch):
    if not BATCH_ID.match(str(batch or "")):
        raise IngestError("That upload batch is not known.")
    folder = Path(root) / batch
    if not folder.is_dir():
        raise IngestError("That upload batch is not known. Upload the photos again.")
    return folder


def new_batch(root):
    batch = secrets.token_hex(6)
    (Path(root) / batch).mkdir(parents=True, exist_ok=True)
    return batch


def _public(page):
    return {k: page[k] for k in ("id", "original", "mime", "bytes", "sha256")}


def add_pages(root, batch, files):
    """Keep uploaded photos in a batch. files: [(original name, bytes)]. Returns the batch's pages so far.

    Every file is checked before any is kept, so one bad photo does not leave half an upload behind.
    """
    folder = batch_folder(root, batch)
    pages = _manifest(folder)
    if len(pages) + len(files) > MAX_PAGES:
        raise IngestError(f"At most {MAX_PAGES} pages can be read in one run.")
    checked = []
    for original, data in files:
        name = Path(str(original or "photo")).name[:80] or "photo"
        checked.append((name, data, check_image(data, name)))
    for name, data, mime in checked:
        n = max([int(p["id"][1:]) for p in pages] + [0]) + 1
        pid = f"p{n:02d}"
        ext = ".jpg" if mime == "image/jpeg" else ".png"
        (folder / f"{pid}{ext}").write_bytes(data)
        pages.append({"id": pid, "file": f"{pid}{ext}", "original": name, "mime": mime, "bytes": len(data),
                      "sha256": hashlib.sha256(data).hexdigest()})
    _save_manifest(folder, pages)
    return [_public(p) for p in pages]


def sample_files(data_dir):
    """The sample photographed scripts shipped in data/scripts, in the order golden.json lists them."""
    folder = Path(data_dir) / "scripts"
    if not folder.is_dir():
        return []
    files = sorted(p for p in folder.glob("*") if p.suffix.lower() in (".jpg", ".jpeg", ".png"))
    golden = folder / "golden.json"
    if golden.exists():
        listed = [p["file"] for p in json.loads(golden.read_text(encoding="utf-8")).get("pages", [])]
        files.sort(key=lambda p: listed.index(p.name) if p.name in listed else len(listed))
    return [(p.name, p.read_bytes()) for p in files]


def page_file(root, batch, pid):
    """(path, mime) of one kept photo, or IngestError."""
    folder = batch_folder(root, batch)
    page = next((p for p in _manifest(folder) if p["id"] == pid), None) if PAGE_ID.match(str(pid or "")) else None
    if not page:
        raise IngestError("That page is not in the batch.")
    return folder / page["file"], page["mime"]


def load_pages(root, batch, order=None):
    """The batch's photos, with their bytes, in the order the teacher chose. Pages left out of `order` are not read."""
    folder = batch_folder(root, batch)
    pages = {p["id"]: p for p in _manifest(folder)}
    ids = list(pages) if order is None else [str(i) for i in order]
    unknown = [i for i in ids if i not in pages]
    if unknown:
        raise IngestError(f"Pages not in the batch: {', '.join(unknown)}.")
    if len(set(ids)) != len(ids):
        raise IngestError("A page is listed twice in the order.")
    if not ids:
        raise IngestError("No pages were chosen to read.")
    return [{**pages[i], "data": (folder / pages[i]["file"]).read_bytes()} for i in ids]


def copy_pages(pages, folder):
    """Save copies of the photos a run read, named in reading order."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    for n, p in enumerate(pages, 1):
        stem = re.sub(r"[^\w.-]+", "_", Path(p["original"]).stem)[:40]
        (folder / f"{n:02d}_{p['id']}_{stem}{Path(p['file']).suffix}").write_bytes(p["data"])


def clear_batches(root, keep=20):
    """Remove old upload batches, keeping the newest few."""
    root = Path(root)
    if not root.is_dir():
        return
    batches = sorted((p for p in root.iterdir() if p.is_dir() and BATCH_ID.match(p.name)), key=lambda p: p.stat().st_mtime)
    for old in batches[:-keep]:
        shutil.rmtree(old, ignore_errors=True)
