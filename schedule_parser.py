"""
Parser for UKG "My schedule" PDF printouts.

Works for both kinds of PDF:
  * text PDFs  -> words + coordinates via pdfplumber
  * image PDFs -> words + coordinates via OCR (pdf2image + pytesseract)

Instead of trusting text order (which is scrambled in these PDFs), it uses
word POSITIONS: it rebuilds the lines, splits the two calendar columns, reads
them top-to-bottom / left column then right column, and tracks:
    week header ("November 02 - 08")  ->  weekday label ("Wed")  ->  card
The shift code is the title line sitting directly above a "07:30-15:30 [8.00]"
time line.
"""
import io
import re
from datetime import date, timedelta
from statistics import median

import pdfplumber

# --------------------------------------------------------------------------
# Settings you will probably want to tweak
# --------------------------------------------------------------------------
# Titles that are holidays, not real shifts (compared in UPPER case, "contains")
EXCLUDED_TITLES = ["STATDAY", "STAT DAY", "REMEMBRANCE"]

# Code written to the sheet for an approved time-off request
TIME_OFF_CODE = "V"

# Exact renames applied to the printed shift code (UPPER-case keys)
CODE_ALIASES = {
    "MI": "M1",
    "M I": "M1",
    "E N": "N",
    "EN": "N",
    "VAC PT": "V",
    "VP": "V",
    "TO": "V",
}

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

TIME_RE = re.compile(r"(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})")
WEEKDAY_RE = re.compile(r"^(mon|tue|wed|thu|fri|sat|sun)\.?$", re.I)
WEEK_RE = re.compile(
    r"^([A-Za-z]{3,9})\.?\s+(\d{1,2})\s*[-–—]?\s*(?:([A-Za-z]{3,9})\.?\s+)?(\d{1,2})$")
DAYNUM_RE = re.compile(r"^(\d{1,2})(?:\s+(.+))?$")
ISO_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


# --------------------------------------------------------------------------
# 1. Getting words with coordinates
# --------------------------------------------------------------------------
def _words_from_text_pdf(pdf_bytes):
    pages = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for p in pdf.pages:
            words = [
                dict(text=w["text"], x0=w["x0"], x1=w["x1"], top=w["top"], bottom=w["bottom"])
                for w in p.extract_words(x_tolerance=1.5, y_tolerance=2)
            ]
            pages.append(dict(width=float(p.width), height=float(p.height), words=words, image=None))
    return pages


def _words_from_ocr(pdf_bytes, dpi=300):
    from pdf2image import convert_from_bytes
    import pytesseract

    pages = []
    for img in convert_from_bytes(pdf_bytes, dpi=dpi):
        d = pytesseract.image_to_data(img, config="--psm 11", output_type=pytesseract.Output.DICT)
        words = []
        for i, t in enumerate(d["text"]):
            if t.strip() and float(d["conf"][i]) > 0:
                words.append(dict(text=t.strip(), x0=d["left"][i], x1=d["left"][i] + d["width"][i],
                                  top=d["top"][i], bottom=d["top"][i] + d["height"][i]))
        pages.append(dict(width=float(img.width), height=float(img.height), words=words, image=img))
    return pages


def load_pages(pdf_bytes):
    """Return (pages, method). Uses the text layer when there is one, else OCR."""
    try:
        pages = _words_from_text_pdf(pdf_bytes)
        n_chars = sum(len(w["text"]) for p in pages for w in p["words"])
    except Exception:
        pages, n_chars = [], 0
    if n_chars >= 50:
        return pages, "text layer"
    return _words_from_ocr(pdf_bytes), "OCR"


# --------------------------------------------------------------------------
# 2. Words -> lines (split into columns, then group by vertical position)
# --------------------------------------------------------------------------
def _group_lines(words):
    if not words:
        return []
    h = median(w["bottom"] - w["top"] for w in words)
    tol = max(2.0, 0.5 * h)
    words = sorted(words, key=lambda w: (w["top"] + w["bottom"]) / 2)
    lines, cur, cur_y = [], [], None
    for w in words:
        cy = (w["top"] + w["bottom"]) / 2
        if cur and abs(cy - cur_y) > tol:
            lines.append(cur)
            cur = []
        cur.append(w)
        cur_y = sum((x["top"] + x["bottom"]) / 2 for x in cur) / len(cur)
    if cur:
        lines.append(cur)
    out = []
    for ln in lines:
        ln = sorted(ln, key=lambda w: w["x0"])
        out.append(dict(
            text=" ".join(w["text"] for w in ln),
            words=ln,
            x0=min(w["x0"] for w in ln),
            top=min(w["top"] for w in ln),
            bottom=max(w["bottom"] for w in ln),
        ))
    return out


def _page_lines_in_reading_order(page):
    W, words = page["width"], page["words"]
    mid = W / 2
    # two columns only if nothing straddles the middle of the page
    two_cols = not any(w["x0"] < mid < w["x1"] for w in words)
    if two_cols:
        cols = [[w for w in words if (w["x0"] + w["x1"]) / 2 < mid],
                [w for w in words if (w["x0"] + w["x1"]) / 2 >= mid]]
    else:
        cols = [words]
    lines = []
    for c in cols:
        lines.extend(_group_lines(c))   # each column is sorted top->bottom
    return lines


# --------------------------------------------------------------------------
# 3. Header info: employee name + schedule period
# --------------------------------------------------------------------------
def _header_info(pages):
    all_words = [w for p in pages for w in p["words"]]
    iso = ISO_RE.findall(" ".join(w["text"] for w in all_words))
    start = end = None
    if len(iso) >= 2:
        start, end = date.fromisoformat(iso[0]), date.fromisoformat(iso[1])
    elif len(iso) == 1:
        start = date.fromisoformat(iso[0])
        end = date(start.year + (start.month == 12), (start.month % 12) + 1, 1) - timedelta(days=1)

    name = ""
    if pages:
        first = pages[0]["words"]
        mys = [w for w in first if w["text"].lower() == "my"]
        if mys:
            my = min(mys, key=lambda w: w["top"])
            cy = (my["top"] + my["bottom"]) / 2
            row = sorted((w for w in first if abs((w["top"] + w["bottom"]) / 2 - cy) < 0.8 * (my["bottom"] - my["top"])),
                         key=lambda w: w["x0"])
            toks = [w["text"] for w in row]
            # everything after the last ISO date token
            idx = max((i for i, t in enumerate(toks) if ISO_RE.fullmatch(t)), default=-1)
            tail = [re.sub(r"[^A-Za-z'\-]", "", t) for t in toks[idx + 1:]]
            tail = [t for t in tail if len(t) >= 2]
            if tail and re.fullmatch(r"[A-Z]{2}", tail[0]):   # avatar initials
                tail = tail[1:]
            elif tail and re.fullmatch(r"[A-Z]{2}", tail[-1]):  # initials after the name (some PDFs)
                tail = tail[:-1]
            name = " ".join(tail)
    return start, end, name


# --------------------------------------------------------------------------
# 4. Helpers
# --------------------------------------------------------------------------
def _clean(text):
    """Drop icon glyphs / stray symbols, keep letters, digits and shift-code punctuation."""
    t = re.sub(r"[^A-Za-z0-9\s\-\+\[\]\.:/'()]", " ", text)
    return re.sub(r"\s+", " ", t).strip()


def _looks_like_code(t):
    if not t or len(t) > 16 or "/" in t or ":" in t:
        return False
    if len(re.findall(r"\d", t)) >= 5:        # employee / job numbers
        return False
    if t.lower() in ("technologist", "laboratory"):
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 \-\+\.]*", t))


def _normalize_code(raw):
    code = raw.strip()
    up = re.sub(r"\s+", " ", code.upper())
    
    if up in CODE_ALIASES:
        return CODE_ALIASES[up]
        
    # Handle "e N" / "E N" / "eN" OCR variations -> "N"
    if re.fullmatch(r"E\s*N", up, re.I):
        return "N"
        
    # Handle "Mi" / "M i" / "M1" OCR variations -> "M1"
    if re.fullmatch(r"M\s*[I1i]", code, re.I):
        return "M1"
        
    if up.startswith("VAC") or up in ("VP", "TO", "V"):
        return "V"
        
    return code


def _is_excluded(raw):
    up = raw.upper()
    return any(x in up for x in EXCLUDED_TITLES)


def _week_from_header(txt, period_start):
    m = WEEK_RE.match(txt)
    if not m:
        return None
    mon = MONTHS.get(m.group(1)[:3].lower())
    if not mon or (len(m.group(1)) > 3 and not m.group(1).lower().startswith(
            [k for k, v in MONTHS.items() if v == mon][0])):
        return None
    year = period_start.year
    if mon - period_start.month >= 6:
        year -= 1
    elif period_start.month - mon >= 6:
        year += 1
    try:
        return date(year, mon, int(m.group(2)))
    except ValueError:
        return None


def _recover_title(page, line_time, x_left):
    """OCR missed the shift-code word: re-read the strip just above the time line."""
    img = page.get("image")
    if img is None:
        return ""
    import pytesseract
    h = line_time["bottom"] - line_time["top"]
    box = (max(0, int(x_left - 4)), max(0, int(line_time["top"] - 2.2 * h)),
           min(img.width, int(x_left + 14 * h)), max(1, int(line_time["top"] - 0.15 * h)))
    crop = img.crop(box).resize(((box[2] - box[0]) * 2, (box[3] - box[1]) * 2))
    txt = pytesseract.image_to_string(
        crop, config="--psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-+ ")
    return _clean(txt)


# --------------------------------------------------------------------------
# 5. Main entry point
# --------------------------------------------------------------------------
def parse_schedule(pdf_bytes):
    """
    Returns dict(name, start, end, method, shifts, skipped)
      shifts  = [{"date": date, "code": str, "time": str, "raw": str}, ...]
      skipped = [str, ...]   things deliberately ignored (holidays etc.)
    """
    pages, method = load_pages(pdf_bytes)
    start, end, name = _header_info(pages)
    if start is None:
        raise ValueError("Could not find the schedule date range (e.g. 2026-11-01 - 2026-11-30).")
    period = [start + timedelta(days=i) for i in range((end - start).days + 1)]

    week_start = None
    cur_date = None
    last_other = None            # (cleaned text, line) of the latest unclassified line
    by_date, skipped = {}, []

    def add(d, code, tm, raw):
        if d is None or d < start or d > end:
            return
        by_date.setdefault(d, [])
        if (code, tm) not in [(c["code"], c["time"]) for c in by_date[d]]:
            by_date[d].append(dict(code=code, time=tm, raw=raw))

    for page in pages:
        for line in _page_lines_in_reading_order(page):
            if line["top"] > 0.94 * page["height"]:      # page footer ("1/1")
                continue
            txt = _clean(line["text"])
            if not txt:
                continue

            # --- week header
            wk = _week_from_header(txt, start)
            if wk:
                week_start, cur_date, last_other = wk, None, None
                continue

            # --- weekday label
            if WEEKDAY_RE.match(txt):
                idx = WEEKDAYS.index(txt[:3].lower())
                cur_date, last_other = None, None
                if week_start:
                    for k in range(7):
                        d = week_start + timedelta(days=k)
                        if d.weekday() == idx:
                            cur_date = d
                            break
                continue

            # --- day number (maybe followed by a title on the same row, e.g. "11 STATDAY")
            if TIME_RE.search(txt) is None:
                m = DAYNUM_RE.match(txt)
                if m and 1 <= int(m.group(1)) <= 31:
                    n = int(m.group(1))
                    cands = [d for d in period if d.day == n]
                    if week_start:
                        in_week = [d for d in cands if 0 <= (d - week_start).days <= 6]
                        cands = in_week or cands
                    if cands:
                        if cur_date and cur_date not in cands:
                            cands.sort(key=lambda d: abs((d - cur_date).days))
                        cur_date = cands[0]
                    rest = _clean(m.group(2) or "")
                    if rest:
                        last_other = (rest, line)
                    continue

            # --- time line -> a shift card
            tm = TIME_RE.search(txt)
            if tm:
                time_str = f"{tm.group(1)}:{tm.group(2)}-{tm.group(3)}:{tm.group(4)}"
                title = None
                lh = max(1.0, line["bottom"] - line["top"])
                if last_other and (line["top"] - last_other[1]["bottom"]) < 2.2 * lh \
                        and _looks_like_code(last_other[0]):
                    title = last_other[0]
                if title is None:
                    title = _recover_title(page, line, line["x0"]) or "??"
                if _is_excluded(title):
                    skipped.append(f"{cur_date}: {title} ({time_str}) – holiday, excluded")
                else:
                    add(cur_date, _normalize_code(title), time_str, title)
                last_other = None
                continue

            # --- approved time-off card
            if re.search(r"approved|time-?\s?off", txt, re.I):
                add(cur_date, TIME_OFF_CODE, "", txt)
                last_other = None
                continue

            last_other = (txt, line)

    shifts = []
    for d in sorted(by_date):
        items = by_date[d]
        shifts.append(dict(
            date=d,
            code="/".join(dict.fromkeys(i["code"] for i in items)),
            time=" & ".join(i["time"] for i in items if i["time"]),
            raw=" | ".join(i["raw"] for i in items),
        ))
    return dict(name=name, start=start, end=end, method=method, shifts=shifts, skipped=skipped)


if __name__ == "__main__":
    import sys
    for f in sys.argv[1:]:
        r = parse_schedule(open(f, "rb").read())
        print("==", f, "|", r["method"], "|", r["name"], "|", r["start"], "->", r["end"])
        for s in r["shifts"]:
            print(f"  {s['date']}  {s['code']:<6} {s['time']}")
        for s in r["skipped"]:
            print("  skipped:", s)
