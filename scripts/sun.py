#!/usr/bin/env python3
"""
Human-made objects orbiting the Sun, for the map's Sun view (round 209o,
asked 15 October 2026: "a layer of human-made objects orbiting the Sun, such
as spent rocket stages and dead probes").

Source: Jonathan McDowell's General Catalog of Artificial Space Objects
(GCAT), its Heliocentric Register, hcocat.tsv, every row and every column as
GCAT gives it (GCAT is released under the Creative Commons CC-BY licence:
J. McDowell, planet4589.org/space/gcat).

Where each one is now: NASA/JPL's Horizons system (a US government service,
public domain), asked once a day for each object it follows, by the object's
international designator (GCAT's Piece) and then by its name. Only an exact
match is taken. Where Horizons' record for an object ends before today, the
last position it gives is used and dated. Objects Horizons does not follow are
kept, with no position, and listed in the view as having none. Nothing is
estimated.

The planets' places today and their paths round the Sun come from Horizons too.

Writes:
  bodies/sun_objects.json   {"objects": [ {gcat: {...every column...},
                              pos: {x, y, z, date, last} | null,
                              horizons: {spkid, name} | null}, ... ],
                             "built": ..., "source": ...}
  bodies/sun_planets.json   {"planets": [{name, now: [x, y, z], path: [[x, y, z], ...]}], "date": ...}
Positions are heliocentric, ecliptic of J2000, in astronomical units.
"""
import datetime, json, pathlib, re, sys, time, urllib.parse, urllib.request
from html.parser import HTMLParser

GCAT = "https://planet4589.org/space/gcat/tsv/cat/hcocat.tsv"
LOOKUP = "https://ssd.jpl.nasa.gov/api/horizons_lookup.api"
EPHEM = "https://ssd.jpl.nasa.gov/api/horizons.api"
OUT = pathlib.Path("bodies")
CACHE = OUT / "sun_horizons_ids.json"      # name -> spkid (or null), so names are looked up once
UA = {"User-Agent": "Culprits atlas build (welcometoyourgalaxy@gmail.com)"}
MONTHS = {m: i + 1 for i, m in enumerate(["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"])}
PLANETS = [("Mercury", "199", 87.97), ("Venus", "299", 224.70), ("Earth", "399", 365.26), ("Mars", "499", 686.98),
           ("Jupiter", "599", 4332.6), ("Saturn", "699", 10759.2), ("Uranus", "799", 30688.5), ("Neptune", "899", 60182.0)]


def get(url, tries=4):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            if i == tries - 1:
                raise
            print(f"  retry {url[:90]}: {e}", flush=True)
            time.sleep(5 * (i + 1))


def gcat_rows():
    text = get(GCAT)
    head, rows = None, []
    for line in text.splitlines():
        if not line.strip():
            continue
        if line.startswith("#"):
            if head is None and "JCAT" in line:
                head = [h.strip() for h in line.lstrip("#").split("\t")]
            continue
        cells = [c.strip() for c in line.split("\t")]
        if head is None:
            sys.exit("sun: the catalogue's header line was not found")
        rows.append({h: (cells[i] if i < len(cells) else "") for i, h in enumerate(head)})
    return head, rows


def lookup(sstr, cache):
    if sstr in cache:
        return cache[sstr]
    q = urllib.parse.urlencode({"sstr": sstr, "group": "sct", "format": "json"})
    try:
        d = json.loads(get(f"{LOOKUP}?{q}"))
    except Exception as e:  # noqa: BLE001
        print(f"  lookup failed for {sstr}: {e}")
        return None            # not cached: asked again tomorrow
    time.sleep(0.4)
    want = norm(sstr)
    hit = None
    for r in d.get("result") or []:
        names = [r.get("name") or ""] + list(r.get("alias") or [])
        if any(norm(n) == want for n in names):
            hit = {"spkid": str(r.get("spkid")), "name": r.get("name")}
            break
    cache[sstr] = hit
    return hit


def norm(s):
    s = re.sub(r"\(spacecraft\)", "", str(s), flags=re.I)
    return re.sub(r"[^a-z0-9]", "", s.lower())


# Round 213o (asked 15 October: leave out the craft still working, which NASA's
# Eyes on the Solar System already shows): the names on Wikipedia's "List of
# active Solar System probes" (CC BY-SA 4.0), read from its table headers,
# bold names and headings. The map leaves out the rows GCAT gives for a payload
# with one of these names (and its parts still attached), and lists them.
ACTIVE_PAGE = "List_of_active_Solar_System_probes"


class Names(HTMLParser):
    """Text inside table headers, bold type, captions and headings."""
    KEEP = {"th", "b", "caption", "h2", "h3", "h4", "dt"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth, self.buf, self.out, self.skip = 0, [], [], 0

    def handle_starttag(self, tag, a):
        if tag in ("sup", "style", "script"):
            self.skip += 1
        if tag in self.KEEP:
            self.depth += 1

    def handle_endtag(self, tag):
        if tag in ("sup", "style", "script") and self.skip:
            self.skip -= 1
        if tag in self.KEEP and self.depth:
            self.depth -= 1
            if not self.depth:
                t = " ".join("".join(self.buf).replace("[edit]", "").split())
                if t:
                    self.out.append(t)
                self.buf = []

    def handle_data(self, d):
        if self.depth and not self.skip:
            self.buf.append(d)


def active_names():
    q = urllib.parse.urlencode({"action": "parse", "page": ACTIVE_PAGE, "prop": "text", "format": "json", "formatversion": 2, "redirects": 1})
    html = json.loads(get(f"https://en.wikipedia.org/w/api.php?{q}"))["parse"]["text"]
    p = Names()
    p.feed(html)
    names = set()
    for t in p.out:
        for part in [t, t.split("(")[0], *re.findall(r"\(([^)]*)\)", t)]:
            part = part.strip(" :;,.")
            if 3 <= len(part) <= 60:
                names.add(part)
    return sorted(names)


def is_active(r, names):
    """The listed name, matched on GCAT's Name or PLName (letters and digits only):
    exactly, or as the start of the name for a payload or a part still attached
    (BepiColombo MPO under BepiColombo); short names (under five letters) only exactly."""
    if not (r.get("Type", "").startswith("P") or r.get("Status") == "AO"):
        return None
    mine = [norm(r.get(k, "")) for k in ("Name", "PLName") if r.get(k) and r[k] != "-"]
    for n in names:
        k = norm(n)
        if len(k) < 3:
            continue
        for m in mine:
            if m == k or (len(k) >= 5 and m.startswith(k)):
                return n
    return None


def vectors(command, start, stop, step):
    q = urllib.parse.urlencode({
        "format": "json", "COMMAND": f"'{command}'", "OBJ_DATA": "'NO'", "MAKE_EPHEM": "'YES'", "EPHEM_TYPE": "'VECTORS'",
        "CENTER": "'500@10'", "START_TIME": f"'{start}'", "STOP_TIME": f"'{stop}'", "STEP_SIZE": f"'{step}'",
        "REF_PLANE": "'ECLIPTIC'", "REF_SYSTEM": "'ICRF'", "VEC_TABLE": "'1'", "OUT_UNITS": "'AU-D'", "CSV_FORMAT": "'YES'",
        "VEC_LABELS": "'NO'"})
    text = json.loads(get(f"{EPHEM}?{q}")).get("result", "")
    time.sleep(0.4)
    if "$$SOE" not in text:
        return None, text
    body = text.split("$$SOE", 1)[1].split("$$EOE", 1)[0]
    out = []
    for line in body.strip().splitlines():
        c = [x.strip() for x in line.split(",")]
        if len(c) >= 5:
            try:
                out.append((c[1], float(c[2]), float(c[3]), float(c[4])))
            except ValueError:
                pass
    return out, text


def where(spkid, today):
    """Today's place; if Horizons' record ends before today, its last one, dated."""
    tomorrow = (datetime.date.fromisoformat(today) + datetime.timedelta(days=1)).isoformat()
    got, text = vectors(spkid, today, tomorrow, "1 d")
    if got:
        d, x, y, z = got[0]
        return {"x": x, "y": y, "z": z, "date": today, "last": False}
    m = re.search(r"after A\.D\. (\d{4})-([A-Z]{3})-(\d{2})", text)
    if m:
        end = datetime.date(int(m.group(1)), MONTHS[m.group(2)], int(m.group(3)))
        a, b = (end - datetime.timedelta(days=1)).isoformat(), end.isoformat()
        got, _ = vectors(spkid, a, b, "1 d")
        if got:
            d, x, y, z = got[-1]
            return {"x": x, "y": y, "z": z, "date": a, "last": True}
    return None


def main():
    OUT.mkdir(exist_ok=True)
    today = datetime.date.today().isoformat()
    cache = {}
    if CACHE.exists():
        try:
            cache = json.loads(CACHE.read_text())
        except ValueError:
            cache = {}
    head, rows = gcat_rows()
    print(f"sun: {len(rows)} objects in GCAT's Heliocentric Register")
    try:
        names = active_names()
        print(f"sun: {len(names)} names read from Wikipedia's {ACTIVE_PAGE}: " + "; ".join(names))
    except Exception as e:  # noqa: BLE001
        names = None
        print(f"sun: Wikipedia's {ACTIVE_PAGE} could not be read ({e}); no row is marked as working")
    objects, placed = [], 0
    for r in rows:
        hit = None
        tries = []
        piece = r.get("Piece", "")
        if re.match(r"^\d{4}-\d{3}[A-Z]+$", piece):
            tries.append(piece)
        for k in ("Name", "PLName"):
            if r.get(k) and r[k] != "-":
                tries.append(r[k])
        for t in tries:
            hit = lookup(t, cache)
            if hit:
                break
        pos = None
        if hit:
            try:
                pos = where(hit["spkid"], today)
            except Exception as e:  # noqa: BLE001
                print(f"  {r.get('Name')}: Horizons did not answer ({e})")
        placed += 1 if pos else 0
        rec = {"gcat": r, "pos": pos, "horizons": hit}
        act = is_active(r, names) if names else None
        if act:
            rec["active"] = act
        objects.append(rec)
    planets = []
    for name, cmd, period in PLANETS:
        stop = (datetime.date.fromisoformat(today) + datetime.timedelta(days=int(period) + 1)).isoformat()
        try:
            path, _ = vectors(cmd, today, stop, "180")
        except Exception as e:  # noqa: BLE001
            print(f"  {name}: {e}")
            path = None
        if path:
            planets.append({"name": name, "now": list(path[0][1:]), "path": [list(p[1:]) for p in path]})
    CACHE.write_text(json.dumps(cache, indent=0, sort_keys=True))
    src = ("Objects: J. McDowell, General Catalog of Artificial Space Objects (GCAT), Heliocentric Register, "
           "planet4589.org/space/gcat (CC BY). Places: NASA/JPL Horizons, ssd.jpl.nasa.gov/horizons.")
    act = {"page": f"https://en.wikipedia.org/wiki/{ACTIVE_PAGE}", "names": names,
           "rows": sum(1 for o in objects if o.get("active"))} if names is not None else None
    if act:
        print(f"sun: {act['rows']} rows marked as working craft: " + "; ".join(sorted({o['gcat'].get('Name', '') for o in objects if o.get('active')})))
    (OUT / "sun_objects.json").write_text(json.dumps({"objects": objects, "columns": head, "built": today, "source": src, "active": act}, ensure_ascii=False))
    (OUT / "sun_planets.json").write_text(json.dumps({"planets": planets, "date": today,
                                                      "source": "NASA/JPL Horizons, heliocentric ecliptic J2000, astronomical units"}))
    print(f"sun: {placed} of {len(objects)} placed by Horizons; {len(planets)} planets")


if __name__ == "__main__":
    main()
