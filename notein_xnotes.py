#!/usr/bin/env python3
"""Convert Notein notes (.in) to xnotes notes (.xnote) and back, keeping handwriting as vector strokes.

    python notein_xnotes.py "My note.in"              # -> My note.xnote
    python notein_xnotes.py "My note.xnote"           # -> My note.in
    python notein_xnotes.py *.in -o converted/        # batch
    python notein_xnotes.py note.in --no-background   # drop the page background (PDF/template)
    python notein_xnotes.py note.in --ink pen         # plain xnotes pen instead of natural ink

Only the Python standard library is needed (Python 3.8+).
"""
import argparse
import io
import json
import math
import os
import shutil
import sqlite3
import struct
import sys
import tempfile
import time
import uuid
import zipfile
from collections import Counter

DPI = 150  # xnotes content px per inch; Notein's page space (A4 = 1240 x 1753) is the same
NOTEIN_FILES = "/data/user/0/com.orion.notein.global/files"
ROOM_VERSION, ROOM_HASH = 34, "6fb07f1830e43b74e35643c931edda69"
ZDATE = (2020, 1, 1, 0, 0, 0)

# ----------------------------------------------------------------------------- pressure / smoothing
K = 8.0  # xnotes' pressure S-curve steepness (StrokeEngine.PRESSURE_CURVE_K)
_LO, _HI = 1 / (1 + math.exp(K / 2)), 1 / (1 + math.exp(-K / 2))


def ease(p):
    """xnotes' pressure response: stored pressure -> effective width fraction."""
    return (1 / (1 + math.exp(-K * (p - 0.5))) - _LO) / (_HI - _LO)


def ease_inv(e):
    """Pressure to store in xnotes so that it draws with a linear response to e."""
    s = min(max(e, 1e-6), 1 - 1e-6) * (_HI - _LO) + _LO
    return min(max(0.5 - math.log(1 / s - 1) / K, 0.0), 1.0)


def catmull_rom(pts, spacing=0.75):
    """Resample (x, y, p) points along a centripetal Catmull-Rom spline (smooth curves, no corners)."""
    clean = [pts[0]]
    for p in pts[1:]:
        if math.hypot(p[0] - clean[-1][0], p[1] - clean[-1][1]) > 0.05:
            clean.append(p)
    if len(clean) < 3:
        return clean
    ext = [tuple(2 * a - b for a, b in zip(clean[0], clean[1]))] + clean + \
          [tuple(2 * a - b for a, b in zip(clean[-1], clean[-2]))]
    out = [clean[0]]
    for i in range(1, len(ext) - 2):
        p0, p1, p2, p3 = ext[i - 1:i + 3]
        t = [0.0]
        for a, b in ((p0, p1), (p1, p2), (p2, p3)):
            t.append(t[-1] + max(math.hypot(b[0] - a[0], b[1] - a[1]), 1e-6) ** 0.5)
        t0, t1, t2, t3 = t
        n = max(1, round(math.hypot(p2[0] - p1[0], p2[1] - p1[1]) / spacing))  # dense input stays as is
        for k in range(1, n + 1):
            u = t1 + (t2 - t1) * k / n
            lerp = lambda a, b, ta, tb: [((tb - u) * x + (u - ta) * y) / (tb - ta) for x, y in zip(a[:2], b[:2])]
            a1, a2, a3 = lerp(p0, p1, t0, t1), lerp(p1, p2, t1, t2), lerp(p2, p3, t2, t3)
            b1, b2 = lerp(a1, a2, t0, t2), lerp(a2, a3, t1, t3)
            c = lerp(b1, b2, t1, t2)
            out.append((c[0], c[1], p1[2] + (p2[2] - p1[2]) * k / n))
    return out


# ----------------------------------------------------------------------------- small helpers
def argb_to_rgba(c):
    c &= 0xFFFFFFFF
    return [(c >> 16) & 255, (c >> 8) & 255, c & 255, (c >> 24) & 255]


def rgba_to_argb(rgba):
    r, g, b, a = (list(rgba) + [255])[:4]
    v = (a << 24) | (r << 16) | (g << 8) | b
    return v - (1 << 32) if v >= 1 << 31 else v


def colorlong_to_rgba(v):
    """Android ColorLong (as stored by androidx.ink) -> [r, g, b, a]."""
    u = v & ((1 << 64) - 1)
    if u & 0x3F == 0:
        return argb_to_rgba(u >> 32)
    half = lambda x: struct.unpack("<e", struct.pack("<H", x & 0xFFFF))[0]
    rgb = [max(0, min(255, round(half(u >> s) * 255))) for s in (48, 32, 16)]
    return rgb + [round(((u >> 6) & 0x3FF) / 1023 * 255)]


def png_size(data):
    return struct.unpack(">II", data[16:24]) if data[:8] == b"\x89PNG\r\n\x1a\n" else (0, 0)


def r2(v, s=100):
    return round(v * s) / s


def warn(msg):
    print("  warning:", msg, file=sys.stderr)


# ----------------------------------------------------------------------------- Notein ink blobs
def _varint(b, i):
    v = s = 0
    while True:
        c = b[i]; i += 1
        v |= (c & 0x7F) << s; s += 7
        if c < 0x80:
            return v, i


def decode_ink_blob(b):
    """Notein's protobuf ink stroke: f4 width, f5 ColorLong, f7 brush, f10 (x,y) float32 pairs,
    f11 5 floats/point (t, pressure, ...), f13 3x3 matrix whose translation maps to page coords."""
    d, i = {}, 0
    while i < len(b):
        key, i = _varint(b, i)
        f, wt = key >> 3, key & 7
        if wt == 0:
            v, i = _varint(b, i)
        elif wt == 1:
            v, i = b[i:i + 8], i + 8
        elif wt == 2:
            n, i = _varint(b, i)
            v, i = b[i:i + n], i + n
        elif wt == 5:
            v, i = b[i:i + 4], i + 4
        else:
            raise ValueError("bad protobuf wire type")
        floats = lambda raw: struct.unpack("<%df" % (len(raw) // 4), raw)
        if f == 4: d["width"] = struct.unpack("<f", v)[0]
        elif f == 5: d["color"] = v - (1 << 64) if v >= 1 << 63 else v
        elif f == 7: d["brush"] = v.decode(errors="replace")
        elif f == 10: d["xy"] = floats(v)
        elif f == 11: d["attrs"] = floats(v)
        elif f == 13: d["matrix"] = floats(v)
    xy, attrs, m = d.get("xy", ()), d.get("attrs", ()), d.get("matrix")
    n = len(xy) // 2
    per = len(attrs) // n if n else 0
    tx, ty = (m[2], m[5]) if m and len(m) >= 6 else (0.0, 0.0)
    pts = []
    for k in range(n):
        p = attrs[k * per + 1] if per >= 2 else 1.0
        pts.append((xy[2 * k] + tx, xy[2 * k + 1] + ty, p if 0.0 <= p <= 1.0 else 1.0))
    brush = d.get("brush", "")
    kind = "highlighter" if ("highlight" in brush or "marker" in brush) else "pen"
    return kind, colorlong_to_rgba(d.get("color", 0xFF000000 << 32)), d.get("width", 2.4), pts


# ============================================================================= Notein -> xnotes
def stroke_item(kind, rgba, width, pts, ink):
    if kind == "highlighter":
        return {"kind": "stroke", "tool": "highlighter",
                "config": {"base_width": r2(width, 1000), "pressure_enabled": False, "pressure_min_factor": 1.0,
                           "direction_strength": 0.0, "rgba": rgba, "highlighter_alpha": 0.35},
                "samples": [[r2(x), r2(y), 1.0] for x, y, _ in pts]}
    if ink == "natural":
        # Tapered ends that follow the real pen pressure (xnotes' calligraphy tool with no slant;
        # its pen rounds every end at full width), smooth curves and a linear pressure response.
        pts = [(x, y, ease_inv(p)) for x, y, p in catmull_rom(pts)]
        tool, m = "calligraphy", 0.15
    else:
        tool, m = "pen", 0.35
    return {"kind": "stroke", "tool": tool,
            "config": {"base_width": r2(width, 1000), "pressure_enabled": True, "pressure_min_factor": m,
                       "direction_strength": 0.0, "rgba": rgba},
            "samples": [[r2(x), r2(y), r2(min(max(p, 0.0), 1.0), 1000)] for x, y, p in pts]}


def notein_to_xnote(src, dst, background=True, ink="natural"):
    zin = zipfile.ZipFile(src)
    names = set(zin.namelist())
    meta = json.loads(zin.read("note_meta.json")) if "note_meta.json" in names else {}
    db_name = next((n for n in names if n.startswith("note_database_") and n.endswith("_db")), None)
    if not db_name:
        raise ValueError("no note database inside; is this a Notein .in export?")
    tmp = tempfile.mkdtemp()
    try:
        db_path = os.path.join(tmp, "note.db")
        for suffix in ("", "-wal"):  # a non-empty write-ahead log holds recent edits
            if db_name + suffix in names:
                with open(db_path + suffix, "wb") as f:
                    f.write(zin.read(db_name + suffix))
        db = sqlite3.connect(db_path)
        db.row_factory = sqlite3.Row
        return _notein_db_to_xnote(db, zin, names, meta, dst, background, ink)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _notein_db_to_xnote(db, zin, names, meta, dst, background, ink):
    q = lambda sql, *a: db.execute(sql, a).fetchall()
    note = (q("select * from NoteContentEntity where id = ?", meta.get("id")) or
            q("select * from NoteContentEntity order by last_modification_time desc"))[0]
    pages_in = [r for pid in json.loads(note["page_list"] or "[]")
                for r in q("select * from PageEntity where id = ? and is_in_trash_bin = 0", pid)]
    hidden = {r["id"] for r in q("select id from PageLayerEntity where visible = 0")}

    themes = [json.loads(p["paper_theme"] or "{}") for p in pages_in]
    pdf_of = lambda t: "note_local_uri_theme_" + os.path.basename(t.get("pdfInfo", {}).get("pdfPath", ""))
    used = Counter(pdf_of(t) for t in themes if "PdfPaperTheme" in t.get("type", "") and pdf_of(t) in names)
    source_pdf = used.most_common(1)[0][0] if (background and used) else None
    if background and len(used) > 1:
        warn("pages use several background PDFs; xnotes holds one, the others are left blank")
    if background and any("PdfPaperTheme" not in t.get("type", "PdfPaperTheme") for t in themes):
        warn("non-PDF paper templates are not converted (pages left plain)")

    assets, pages, n = [], [], Counter()
    for page, theme in zip(pages_in, themes):
        pid = page["id"]
        spec = json.loads(page["paper_spec"] or "{}")
        w, h = float(spec.get("width") or 1240), float(spec.get("height") or 1753)
        if page["page_orientation"] == "HORIZONTAL" and h > w:
            w, h = h, w
        items = []  # (z, time, item, bbox)
        for r in q("select * from ImageEntity where page_id = ?", pid):
            name = "note_image_" + os.path.basename(r["uri"])
            if name not in names or r["layer_id"] in hidden:
                continue
            data = zin.read(name)
            sw, sh = png_size(data)
            aname = "assets/image-%03d%s" % (len(assets), os.path.splitext(name)[1] or ".png")
            assets.append((aname, data))
            it = {"kind": "image", "asset": aname, "src_w": sw, "src_h": sh,
                  "rect": [r["left"], r["top"], r["right"] - r["left"], r["bottom"] - r["top"]]}
            if r["rotation"]:
                it["angle"] = r["rotation"]
            items.append((0, r["creation_time"], it)); n["images"] += 1
        for r in q("select * from ShapeEntity where page_id = ?", pid):
            pts = [(p["x"], p["y"]) for p in json.loads(r["points"])]
            if r["layer_id"] in hidden or len(pts) < 2:
                continue
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            it = {"kind": "shape", "shape": "line" if len(pts) == 2 else "polyline",
                  "start": list(pts[0]) if len(pts) == 2 else [min(xs), min(ys)],
                  "end": list(pts[1]) if len(pts) == 2 else [max(xs), max(ys)],
                  "stroke_rgba": argb_to_rgba(r["color"]), "stroke_width": r["width"], "fill_rgba": None}
            if len(pts) > 2:
                it["points"] = [list(p) for p in pts]
            items.append((1, r["creation_time"], it)); n["shapes"] += 1
        for r in q("select * from StrokeEntity where page_id = ?", pid):
            if r["layer_id"] in hidden:
                continue
            if r["record_json"]:
                rec = json.loads(r["record_json"])
                pts = [(p["x"], p["y"], min(max(p.get("p", 1.0), 0.0), 1.0)) for p in rec.get("points", [])]
                kind = "highlighter" if rec.get("type") == 2 else "pen"
                rgba, width = argb_to_rgba(rec.get("color", -16777216)), rec.get("width", 3.0)
            elif r["ink_stroke_blob"]:
                kind, rgba, width, pts = decode_ink_blob(r["ink_stroke_blob"])
            else:
                n["skipped strokes"] += 1
                continue
            if pts:
                items.append((1, r["creation_time"], stroke_item(kind, rgba, width, pts, ink))); n["strokes"] += 1
        n["skipped text boxes"] += len(q("select id from TextBoxEntity where page_id = ?", pid))

        if page["unbounded"]:  # infinite canvas: make a page that fits the content
            warn("unbounded (infinite) page converted to a fixed page around its content")
            w, h = _fit_unbounded(items, w, h)
        is_pdf = source_pdf and "PdfPaperTheme" in theme.get("type", "") and pdf_of(theme) == source_pdf
        items.sort(key=lambda t: (t[0], t[1]))
        pages.append({"width": w, "height": h, "pdf_page": int(theme.get("pageNum", 0)) if is_pdf else None,
                      "items": [t[2] for t in items]})

    if source_pdf:
        assets.append(("assets/source.pdf", zin.read(source_pdf)))
    created = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(note["creation_time"] / 1000))
    manifest = {"format": "xnote", "version": 1, "writer": 67, "created": created, "dpi": DPI,
                "has_pdf": bool(source_pdf), "bookmarks": [], "pages": pages}
    with zipfile.ZipFile(dst, "w") as z:  # assets stored, manifest deflated and last (as xnotes writes it)
        for aname, data in assets:
            z.writestr(zipfile.ZipInfo(aname, ZDATE), data, compress_type=zipfile.ZIP_STORED)
        z.writestr(zipfile.ZipInfo("manifest.json", ZDATE), json.dumps(manifest, separators=(",", ":")),
                   compress_type=zipfile.ZIP_DEFLATED)
    return len(pages), n


def _fit_unbounded(items, w, h, margin=40.0):
    xs, ys = [], []
    for _, _, it in items:
        if it["kind"] == "stroke":
            xs += [s[0] for s in it["samples"]]; ys += [s[1] for s in it["samples"]]
        elif it["kind"] == "image":
            x, y, iw, ih = it["rect"]; xs += [x, x + iw]; ys += [y, y + ih]
        else:
            xs += [it["start"][0], it["end"][0]]; ys += [it["start"][1], it["end"][1]]
    if not xs:
        return w, h
    dx, dy = margin - min(xs), margin - min(ys)
    for _, _, it in items:
        if it["kind"] == "stroke":
            for s in it["samples"]:
                s[0], s[1] = r2(s[0] + dx), r2(s[1] + dy)
        elif it["kind"] == "image":
            it["rect"][0] += dx; it["rect"][1] += dy
        else:
            for key in ("start", "end"):
                it[key] = [it[key][0] + dx, it[key][1] + dy]
            if "points" in it:
                it["points"] = [[x + dx, y + dy] for x, y in it["points"]]
    return max(xs) - min(xs) + 2 * margin, max(ys) - min(ys) + 2 * margin


# ============================================================================= xnotes -> Notein
def blank_pdf(sizes_pt):
    """A minimal PDF with one empty page per (width, height) in points."""
    kids = " ".join("%d 0 R" % (3 + 2 * i) for i in range(len(sizes_pt)))
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [%s] /Count %d >>" % (kids, len(sizes_pt))]
    for i, (w, h) in enumerate(sizes_pt):
        objs.append("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %.2f %.2f] /Resources << >> /Contents %d 0 R >>"
                    % (w, h, 4 + 2 * i))
        objs.append("<< /Length 0 >>\nstream\n\nendstream")
    out, offsets = io.BytesIO(), []
    out.write(b"%PDF-1.4\n")
    for i, o in enumerate(objs):
        offsets.append(out.tell())
        out.write(("%d 0 obj\n%s\nendobj\n" % (i + 1, o)).encode())
    xref = out.tell()
    out.write(("xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)).encode())
    out.write("".join("%010d 00000 n \n" % o for o in offsets).encode())
    out.write(("trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)).encode())
    return out.getvalue()


def _shape_points(it):
    if it.get("points"):
        return [tuple(p[:2]) for p in it["points"]]
    (x0, y0), (x1, y1) = it.get("start", [0, 0]), it.get("end", [0, 0])
    kind = it.get("geom") or it.get("shape")
    if kind in ("rectangle", "rect"):
        return [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
    if kind in ("ellipse", "circle"):
        cx, cy, rx, ry = (x0 + x1) / 2, (y0 + y1) / 2, abs(x1 - x0) / 2, abs(y1 - y0) / 2
        return [(cx + rx * math.cos(a * math.pi / 32), cy + ry * math.sin(a * math.pi / 32)) for a in range(65)]
    return [(x0, y0), (x1, y1)]


def xnote_to_notein(src, dst, background=True, title=None):
    zin = zipfile.ZipFile(src)
    names = set(zin.namelist())
    man = json.loads(zin.read("manifest.json"))
    if man.get("format") != "xnote":
        raise ValueError("not an xnotes document")
    dpi = man.get("dpi", DPI)
    k = DPI / dpi  # Notein coordinates are 150 dpi page px
    now = int(time.time() * 1000)
    note_id = str(uuid.uuid4())
    title = title or os.path.splitext(os.path.basename(dst))[0]
    files, rows, n = {}, {"PageEntity": [], "StrokeEntity": [], "ImageEntity": [], "ShapeEntity": []}, Counter()

    pdf_bg = background and man.get("has_pdf") and "assets/source.pdf" in names
    bg_name = "document_notein_pdf_%s.pdf" % uuid.uuid4()
    blank_name = "document_notein_pdf_%s.pdf" % uuid.uuid4()
    blank_sizes, page_ids = [], []

    def theme(pdf_name, page_num, orient):
        return json.dumps({"type": "com.orion.notein.domain.models.papertheme.PdfPaperTheme",
                           "myTemplateId": str(uuid.uuid4()), "name": "Custom", "orientation": orient,
                           "pageNum": page_num, "pdfInfo": {"id": str(uuid.uuid4()), "tnPath": "",
                                                            "pdfPath": "%s/documents/%s" % (NOTEIN_FILES, pdf_name)}},
                          separators=(",", ":"))

    for page in man.get("pages", []):
        pid = str(uuid.uuid4()); page_ids.append(pid)
        w, h = page.get("width", 1240) * k, page.get("height", 1754) * k
        orient = "HORIZONTAL" if w > h else "VERTICAL"
        if pdf_bg and page.get("pdf_page") is not None:
            th = theme(bg_name, page["pdf_page"], orient)
        else:
            th = theme(blank_name, len(blank_sizes), orient)
            blank_sizes.append((w * 72 / DPI, h * 72 / DPI))
        spec = {"height": round(h), "iconHorizontal": 2131232149, "iconVertical": 2131232150, "info": "",
                "isPercentage": False, "name": "PDF", "width": round(w)}
        rows["PageEntity"].append(dict(
            id=pid, note_id=note_id, paper_spec=json.dumps(spec, separators=(",", ":")), page_orientation=orient,
            paper_theme=th, creation_time=now, last_modification_time=now, tn_path="", unbounded=0, source=1,
            recover_note_id="", recover_note_title="", recover_index=-1, is_in_trash_bin=0,
            paper_padding='{"bottom":0,"left":0,"right":0,"top":0}', padding_color=-1,
            rotation_direction_index=0, is_bookmarked=0, bookmark_time=0))

        t = now
        for it in page.get("items", []):
            t += 1
            kind, iid = it.get("kind"), str(uuid.uuid4())
            if kind == "stroke" or (kind == "shape" and not (it.get("shape") == "line" and not it.get("points"))):
                if kind == "stroke":
                    c = it.get("config", {})
                    hl = it.get("tool") == "highlighter"
                    pr = c.get("pressure_enabled", True) and not hl
                    pts = [(s[0] * k, s[1] * k, ease(s[2] if len(s) > 2 else 1.0) if pr else 1.0)
                           for s in it.get("samples", [])]
                    color, width, typ = c.get("rgba", [0, 0, 0, 255]), c.get("base_width", 3.0) * k, 2 if hl else 0
                else:  # non-line shapes become pen strokes along their outline
                    pts = [(x * k, y * k, 1.0) for x, y in _shape_points(it)]
                    color, width, typ = it.get("stroke_rgba", [0, 0, 0, 255]), it.get("stroke_width", 3.0) * k, 0
                    n["shapes as strokes"] += 1
                if not pts:
                    continue
                last = len(pts) - 1
                points = [{"x": r2(x, 1e4), "y": r2(y, 1e4), "p": r2(p, 1e4),
                           "action": 0 if j == 0 else (1 if j == last else 2)} for j, (x, y, p) in enumerate(pts)]
                b = _bounds([(x, y) for x, y, _ in pts], width / 2)
                rec = {"id": iid, "type": typ, "color": rgba_to_argb(color), "width": width, "points": points,
                       "bounds": dict(zip(("left", "top", "right", "bottom"), b)), "layerId": "default",
                       "creationTime": t}
                rows["StrokeEntity"].append(dict(id=iid, page_id=pid, layer_id="default", creation_time=t,
                                                 record_json=json.dumps(rec, separators=(",", ":")),
                                                 left=b[0], top=b[1], right=b[2], bottom=b[3]))
                n["strokes"] += kind == "stroke"
            elif kind == "shape":  # straight line
                pts = [(it["start"][0] * k, it["start"][1] * k), (it["end"][0] * k, it["end"][1] * k)]
                width = it.get("stroke_width", 3.0) * k
                b = _bounds(pts, width / 2)
                rows["ShapeEntity"].append(dict(
                    id=iid, page_id=pid, color=rgba_to_argb(it.get("stroke_rgba", [0, 0, 0, 255])), width=width,
                    points=json.dumps([{"x": x, "y": y} for x, y in pts]), type=7, blend_mode=-1,
                    layer_id="default", tape_like=0, style=0, opacity_of_fill_color=0, creation_time=t,
                    left=b[0], top=b[1], right=b[2], bottom=b[3], tape_pattern=0))
                n["shapes"] += 1
            elif kind == "image" and it.get("asset") in names:
                ext = os.path.splitext(it["asset"])[1] or ".png"
                if ext == ".svg":
                    n["skipped svg images"] += 1
                    continue
                fname = str(uuid.uuid4()) + ext
                files["note_image_" + fname] = zin.read(it["asset"])
                x, y, iw, ih = [v * k for v in it["rect"]]
                rows["ImageEntity"].append(dict(
                    id=iid, uri="%s/images/%s/%s" % (NOTEIN_FILES, note_id, fname), layer=0, layer_id="default",
                    bounds=json.dumps({"bottom": y + ih, "left": x, "right": x + iw, "top": y}),
                    rotation=float(it.get("angle", 0.0)), page_id=pid, creation_time=t,
                    last_modification_time=t, left=x, top=y, right=x + iw, bottom=y + ih, fixed=0))
                n["images"] += 1
            else:
                n["skipped " + str(kind)] += 1

    if pdf_bg:
        files["note_local_uri_theme_" + bg_name] = zin.read("assets/source.pdf")
    if blank_sizes:
        files["note_local_uri_theme_" + blank_name] = blank_pdf(blank_sizes)

    files["note_database_note_%s_db" % note_id] = _build_notein_db(note_id, page_ids, rows, now)
    files["note_meta.json"] = json.dumps({
        "creationTime": now, "favorite": False, "id": note_id, "inTrashBin": False, "lastModificationTime": now,
        "lastOpenedTime": now, "lockAdded": False, "sortKey": -1, "title": title, "tnHeight": 0, "tnPath": "",
        "tnWidth": 0, "totalPagesCount": len(page_ids), "unboundedNote": False, "userId": "",
        "usingOwnPdf": True}, separators=(",", ":"))
    files["note_in_flag.json"] = '{"OooO00o":true,"OooO0O0":true,"OooO0OO":true,"OooO0Oo":true,"OooO0o0":false}'
    files["note_extra.json"] = '{"OooO00o":53,"OooO0O0":34}'
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            z.writestr(zipfile.ZipInfo(name, ZDATE), data, compress_type=zipfile.ZIP_DEFLATED)
    return len(page_ids), n


def _bounds(pts, pad):
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad


def _build_notein_db(note_id, page_ids, rows, now):
    schema = os.path.join(os.path.dirname(os.path.abspath(__file__)), "notein_schema.sql")
    tmp = tempfile.mkdtemp()
    try:
        path = os.path.join(tmp, "note.db")
        db = sqlite3.connect(path)
        with open(schema, encoding="utf-8") as f:
            db.executescript(f.read())
        db.executescript("CREATE TABLE android_metadata (locale TEXT);"
                         "CREATE TABLE room_master_table (id INTEGER PRIMARY KEY,identity_hash TEXT);")
        db.execute("INSERT INTO android_metadata VALUES ('en_US')")
        db.execute("INSERT INTO room_master_table VALUES (42, ?)", (ROOM_HASH,))
        db.execute("PRAGMA user_version = %d" % ROOM_VERSION)
        db.execute(
            "INSERT INTO NoteContentEntity (id, page_list, page_layer_list, outline_list, default_page_id, "
            "pdf_info_id, saved_page_index, activated_page_layer_id, zoom, unbounded_page_offset_x, "
            "unbounded_page_offset_y, unbounded_note, creation_time, last_modification_time) "
            "VALUES (?, ?, '[\"paper_theme\",\"default\"]', '[]', ?, NULL, 0, 'default', 1.0, 0, 0, 0, ?, ?)",
            (note_id, json.dumps(page_ids), page_ids[0] if page_ids else "", now, now))
        for layer in ("paper_theme", "default"):
            db.execute("INSERT INTO PageLayerEntity (id, note_id, visible) VALUES (?, ?, 1)", (layer, note_id))
        for table, items in rows.items():
            for row in items:
                db.execute("INSERT INTO %s (%s) VALUES (%s)" % (table, ", ".join(row), ", ".join("?" * len(row))),
                           list(row.values()))
        db.commit()
        db.close()
        with open(path, "rb") as f:
            return f.read()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ============================================================================= CLI
def main(argv=None):
    ap = argparse.ArgumentParser(description="Convert Notein notes (.in) to xnotes (.xnote) and back. "
                                             "The direction follows each input's extension.")
    ap.add_argument("inputs", nargs="+", help=".in or .xnote files, or folders (all .in files inside)")
    ap.add_argument("-o", "--output", help="output file (single input) or directory")
    ap.add_argument("--no-background", action="store_true",
                    help="leave out the page background (PDF / paper template); pages become plain")
    ap.add_argument("--ink", choices=["natural", "pen"], default="natural",
                    help="Notein -> xnotes: 'natural' (default) keeps tapered, smooth, ink-like strokes; "
                         "'pen' uses the standard xnotes pen")
    ap.add_argument("-j", "--jobs", type=int, default=os.cpu_count() or 1,
                    help="notes converted in parallel (default: all CPU cores)")
    a = ap.parse_args(argv)
    inputs = []
    for path in a.inputs:
        if os.path.isdir(path):
            inputs += sorted(os.path.join(path, f) for f in os.listdir(path) if f.lower().endswith(".in"))
        else:
            inputs.append(path)
    if not inputs:
        print("no .in files found", file=sys.stderr)
        return 1
    out_dir = a.output if a.output and (len(inputs) > 1 or os.path.isdir(a.output)) else None
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    jobs, failed = [], 0
    for src in inputs:
        stem, ext = os.path.splitext(os.path.basename(src))
        if ext.lower() not in (".in", ".xnote"):
            print("skip %s: expected .in or .xnote" % src, file=sys.stderr); failed += 1
            continue
        new_ext = ".xnote" if ext.lower() == ".in" else ".in"
        dst = (os.path.join(out_dir, stem + new_ext) if out_dir else
               a.output or os.path.join(os.path.dirname(src), stem + new_ext))
        jobs.append((src, dst, not a.no_background, a.ink))

    workers = max(1, min(a.jobs, len(jobs)))
    bar = Progress(len(jobs)) if len(jobs) > 1 else None
    if workers == 1:
        results = (_convert(*j) for j in jobs)
    else:
        from concurrent.futures import ProcessPoolExecutor, as_completed
        pool = ProcessPoolExecutor(workers)
        results = (f.result() for f in as_completed([pool.submit(_convert, *j) for j in jobs]))
    skipped = failed
    for src, dst, pages, n, err in results:
        if err:
            failed += 1
            line = "FAILED %s: %s" % (src, err)
        else:
            line = "%s -> %s  (%d page%s, %s)" % (src, dst, pages, "s" * (pages != 1),
                                                  ", ".join("%d %s" % (v, k) for k, v in n.items() if v) or "empty")
        if bar:
            bar.log(line, err)
        else:
            print(line, file=sys.stderr if err else sys.stdout)
    if bar:
        bar.done(failed - skipped)
    return 1 if failed else 0


def _convert(src, dst, background, ink):
    """One file, in a worker process when converting several; never raises."""
    try:
        if src.lower().endswith(".in"):
            pages, n = notein_to_xnote(src, dst, background=background, ink=ink)
        else:
            stem = os.path.splitext(os.path.basename(src))[0]
            pages, n = xnote_to_notein(src, dst, background=background, title=stem)
        return src, dst, pages, n, None
    except Exception as e:  # reported, and the other files carry on
        return src, dst, 0, Counter(), e


class Progress:
    """A one-line progress bar on stderr (plain log lines when not a terminal)."""

    def __init__(self, total):
        self.total, self.count, self.start = total, 0, time.time()
        self.tty = sys.stderr.isatty()

    def log(self, line, err=None):
        self.count += 1
        if self.tty:
            sys.stderr.write("\r\033[K")
        print(line, file=sys.stderr if err else sys.stdout, flush=True)
        if self.tty:
            width = 30
            filled = width * self.count // self.total
            sys.stderr.write("[%s%s] %d/%d  %.1fs" % ("#" * filled, "-" * (width - filled), self.count,
                                                     self.total, time.time() - self.start))
            sys.stderr.flush()

    def done(self, failed):
        if self.tty:
            sys.stderr.write("\r\033[K")
        print("%d converted, %d failed in %.1fs" % (self.count - failed, failed, time.time() - self.start),
              file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
