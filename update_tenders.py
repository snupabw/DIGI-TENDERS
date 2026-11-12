#!/usr/bin/env python3
"""Collect open tenders from official Botswana websites into tenders.json.
Respects robots.txt, is polite (delay between requests), keeps only facts + a link
to the official notice, and only publishes tenders with a clearly labelled FUTURE closing date.
Run:  python scripts/update_tenders.py          (add --dry to print without writing)"""
import io, json, re, sys, time, hashlib, datetime as dt
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib import robotparser
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
UA = "DigiTendersBot/1.0 (tender reminder service, Palapye Botswana)"
TODAY = dt.date.today()
DELAY = 1.2

MONTHS = {m: i for i, m in enumerate("january february march april may june july august september october november december".split(), 1)}
MONTHS.update({k[:3]: v for k, v in list(MONTHS.items())}); MONTHS["sept"] = 9
DATE_RES = [
    re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?[\s\-/.]+([A-Za-z]{3,9})\.?,?[\s\-/.]+(\d{4})\b"),
    re.compile(r"\b([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b"),
    re.compile(r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})\b"),
]
KEY = re.compile(
    r"(tender closing date|closing date|deadline for (?:the )?submissions? of (?:bids|tenders|proposals|offers)|"
    r"deadline for submission|bid submission deadline|submission deadline|will be closed on|"
    r"tenders? (?:closes|close) on|submit[^.]{0,60}not later than|arrive not later than|closing)", re.I)
BAD = re.compile(r"enquir|querie|clarif|site visit|pre[- ]?tender|release|publication|issue date|available|collection|opening", re.I)
SKIP = re.compile(r"tender is closed|notice of best evaluated bidder|notice of cancellation|notice of direct appointment|"
                  r"notice of award|notice of intention to award|cancellation of tender", re.I)
CITIES = "Gaborone Francistown Palapye Maun Serowe Lobatse Selebi-Phikwe Kasane Molepolole Jwaneng Orapa Letlhakane Mahalapye Kanye Ghanzi Tsabong Shakawe".split()
REF = re.compile(r"\b([A-Z]{2,10}(?:/[A-Z]{2,6})?[ /]?\d{2,6}(?:[/\-]\d{1,4}){1,3})\b")
_robots = {}

def parse_dates(text):
    out = []
    for i, rx in enumerate(DATE_RES):
        for m in rx.finditer(text):
            try:
                if i == 0: d, mo, y = int(m[1]), MONTHS.get(m[2].lower()), int(m[3])
                elif i == 1: mo, d, y = MONTHS.get(m[1].lower()), int(m[2]), int(m[3])
                else: d, mo, y = int(m[1]), int(m[2]), int(m[3])
                if mo: out.append((m.start(), m.end(), dt.date(y, mo, d)))
            except ValueError:
                pass
    return sorted(out)

def time_after(text, pos):
    m = re.match(r"[,\s\-–]*(?:at|by|@)?\s*(\d{1,2})[:h.](\d{2})\b", text[pos:pos + 30]) or \
        re.match(r"[,\s]*(?:at|by|@)?\s*(\d{2})(\d{2})\s*(?:hrs|hours)", text[pos:pos + 30], re.I)
    return f"{int(m[1]):02d}:{m[2]}" if m else ""

def closing_date(text):
    """Return (date, time) of the labelled closing date, or None."""
    text = re.sub(r"\s+", " ", text)
    best = None
    for m in KEY.finditer(text):
        if BAD.search(text[max(0, m.start() - 25):m.end() + 12]):
            continue
        window = text[m.end():m.end() + 90]
        ds = parse_dates(window)
        if ds and ds[0][0] < 110:
            tm = time_after(window, ds[0][1]) or (re.search(r"(\d{1,2})[:h](\d{2})\s*(?:hrs|hours)?\s*(?:on|of)?\s*$", window[:ds[0][0]], re.I) or [None])[0]
            if tm and not re.fullmatch(r"\d{2}:\d{2}", tm):
                mm = re.search(r"(\d{1,2})[:h](\d{2})", tm); tm = f"{int(mm[1]):02d}:{mm[2]}" if mm else ""
            cand = (ds[0][2], tm)
            if best is None or cand[0] > best[0]:
                best = cand
    return best

def classify(text):
    t = text.lower()
    for cat, words in (("construction", "construction building civil road electrical renovation fencing refurbish works contractor borehole pipeline substation".split()),
                       ("ict", "ict software licen network laptop computer cisco firewall server cctv system digital data platform cyber penetration internet it ".split()),
                       ("supplies", "supply delivery stationery equipment goods uniform furniture vehicle fuel reagents consumables toilet".split())):
        if any(w in t for w in words):
            return cat
    return "services"

def find_loc(text, default):
    for c in CITIES:
        if c.lower() in text.lower():
            return c
    return default or "Botswana"

def find_ref(text, fallback):
    m = REF.search(text[:1500])
    return m[1] if m else fallback

def allowed(url):
    p = urlparse(url); host = f"{p.scheme}://{p.netloc}"
    if host not in _robots:
        rp = robotparser.RobotFileParser()
        try:
            r = requests.get(host + "/robots.txt", headers={"User-Agent": UA}, timeout=15)
            if r.status_code == 200: rp.parse(r.text.splitlines())
            elif r.status_code < 500: rp.parse([])
            else: rp.disallow_all = True
        except requests.RequestException:
            rp.disallow_all = True
        _robots[host] = rp
    return _robots[host].can_fetch(UA, url)

def get(url):
    if not allowed(url):
        raise PermissionError("blocked by robots.txt")
    time.sleep(DELAY)
    r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
    r.raise_for_status()
    return r

def page_text(r):
    if "pdf" in r.headers.get("content-type", "").lower() or r.url.lower().endswith(".pdf"):
        from pypdf import PdfReader
        rd = PdfReader(io.BytesIO(r.content))
        return " ".join((pg.extract_text() or "") for pg in rd.pages[:4]), ""
    soup = BeautifulSoup(r.text, "html.parser")
    for t in soup(["script", "style", "nav", "footer"]): t.decompose()
    h = soup.find("h1")
    return soup.get_text(" ", strip=True), (h.get_text(" ", strip=True) if h else "")

def make(src, title, d, tm, url, text=""):
    title = re.sub(r"^(tender|public notice)\s*[-–:]\s*", "", re.sub(r"\s+", " ", title).strip(" -–:|*"), flags=re.I)[:200]
    return {"ref": find_ref(title + " " + text, src["id"].upper() + "-" + hashlib.sha1(url.encode()).hexdigest()[:6]),
            "t": title, "org": src["org"], "cat": classify(title), "loc": find_loc(title + " " + text[:600], src.get("loc")),
            "d": d.isoformat(), "time": tm or "", "src": url, "from": src["id"]}

def inline_items(src, soup, base):
    """Listing pages that show 'Closing Date: ...' beside every tender (e.g. BPC, BDC)."""
    cl = re.compile(r"closing date", re.I); tags = ["li", "article", "tr", "div", "p"]
    hits = [e for e in soup.find_all(tags) if cl.search(e.get_text(" ", strip=True)) and len(e.get_text(" ", strip=True)) <= 600]
    out = []
    for e in hits:
        if any(c is not e and c in hits for c in e.find_all(tags)): continue
        txt = re.sub(r"\s+", " ", e.get_text(" ", strip=True))
        tail = re.split(r"closing date:?", txt, maxsplit=1, flags=re.I)[-1]
        head, box = re.split(r"closing date:?", txt, maxsplit=1, flags=re.I)[0], e
        for _ in range(2):
            if len(head.strip()) >= 12 or box.parent is None: break
            box = box.parent
            head = re.split(r"closing date:?", re.sub(r"\s+", " ", box.get_text(" ", strip=True)), maxsplit=1, flags=re.I)[0]
        ds = parse_dates(tail[:60])
        if not ds or ds[0][2] < TODAY or len(head) < 12: continue
        a = e.find("a", href=True) or box.find("a", href=True)
        out.append(make(src, head, ds[0][2], time_after(tail, ds[0][1]), urljoin(base, a["href"]) if a else base, txt))
    return out

def collect(src):
    r = get(src["url"]); soup = BeautifulSoup(r.text, "html.parser"); items = []
    if src.get("mode", "detail") == "inline":
        return inline_items(src, soup, src["url"])
    pat = re.compile(src["link_pattern"]); seen = set()
    for a in soup.find_all("a", href=True):
        url = urljoin(src["url"], a["href"]).split("#")[0]
        if url in seen or url.rstrip("/") == src["url"].rstrip("/") or not pat.search(url): continue
        seen.add(url)
        if len(seen) > src.get("max_links", 40): break
        try:
            text, h1 = page_text(get(url))
        except Exception as e:
            print("   skip", url[:80], "-", str(e)[:60]); continue
        if SKIP.search(text): continue
        cd = closing_date(text)
        if not cd or cd[0] < TODAY: continue
        title = a.get_text(" ", strip=True)
        if len(title) < 15: title = h1 if len(h1) > 15 else (BeautifulSoup(r.text, "html.parser").title or {"string": url}).string
        items.append(make(src, title, cd[0], cd[1], url, text))
    return items

def main():
    dry = "--dry" in sys.argv
    cfg = json.loads((ROOT / "sources.json").read_text(encoding="utf-8"))
    found, status = {}, []
    for s in cfg["sources"]:
        if not s.get("enabled", True): continue
        print("→", s["org"])
        try:
            items = collect(s)
            status.append({"id": s["id"], "org": s["org"], "ok": True, "open": len(items)})
            for it in items: found[it["src"]] = it
            print("   open tenders found:", len(items))
        except Exception as e:
            status.append({"id": s["id"], "org": s["org"], "ok": False, "note": str(e)[:120]})
            print("   FAILED:", e)
    tenders = sorted(found.values(), key=lambda x: x["d"])
    out_path = ROOT / "tenders.json"
    old = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else {}
    new = {"generated": old.get("generated"), "tenders": tenders, "sources": status}
    if new["tenders"] != old.get("tenders") or new["sources"] != old.get("sources") or not old.get("generated"):
        new["generated"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes")
    print(f"Total open tenders: {len(tenders)}")
    if not dry:
        out_path.write_text(json.dumps(new, indent=1, ensure_ascii=False), encoding="utf-8")

if __name__ == "__main__":
    main()
