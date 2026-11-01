#!/usr/bin/env python3
"""
Fishing vessels on the blacklists for illegal, unreported and unregulated
(IUU) fishing (round 101b, asked 28 September).

Source: the Combined IUU Vessel List, kept by Trygg Mat Tracking (TMT) with
the International MCS Network (iuu-vessels.org): every vessel on the IUU lists
of the regional fisheries management organisations (RFMOs), with each one's
flag, owner, operator, name and flag history and listing history. Its
disclaimer asks that everything taken from it be credited to it.

Every vessel page linked from the list's search page is read, and every field
on it kept:

  iuu/vessels.json    one record per vessel, every field and history table
  iuu/flags.json      ISO3 -> {value: vessels flying that flag now, x_...}
                      (the vessels whose current flag is unknown or not a
                      country are counted in iuu/build.json, not dropped
                      silently)
  iuu/positions.geojson  the vessels whose page gives a last known position
  iuu/build.json      counts, flags not matched to a country, fields seen

Weekly (Mondays) or by hand.
"""
import subprocess, datetime, html, json, os, pathlib, re, sys, time, urllib.parse, urllib.request

BASE = "https://iuu-vessels.org"
UA = {"User-Agent": "Mozilla/5.0 (Culprits atlas build; welcometoyourgalaxy@gmail.com)"}
NOMI = {"User-Agent": "Culprits atlas build (WelcomeToYourGalaxy; welcometoyourgalaxy@gmail.com)"}
OUT = pathlib.Path("iuu")
NE = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_0_countries.geojson"
# Flags as the list may write them, where Natural Earth names the country otherwise.
ALIAS = {"korea, republic of": "KOR", "republic of korea": "KOR", "south korea": "KOR", "korea (republic of)": "KOR",
         "korea, democratic people's republic of": "PRK", "north korea": "PRK", "russian federation": "RUS", "russia": "RUS",
         "taiwan": "TWN", "chinese taipei": "TWN", "viet nam": "VNM", "vietnam": "VNM", "iran": "IRN", "iran, islamic republic of": "IRN",
         "bolivia": "BOL", "tanzania": "TZA", "united republic of tanzania": "TZA", "syria": "SYR", "syrian arab republic": "SYR",
         "cote d'ivoire": "CIV", "côte d'ivoire": "CIV", "ivory coast": "CIV", "equatorial guinea": "GNQ", "sao tome and principe": "STP",
         "são tomé and príncipe": "STP", "saint vincent and the grenadines": "VCT", "st vincent and the grenadines": "VCT",
         "saint kitts and nevis": "KNA", "united states": "USA", "united states of america": "USA", "usa": "USA",
         "united kingdom": "GBR", "belize": "BLZ", "panama": "PAN", "togo": "TGO", "sierra leone": "SLE", "cambodia": "KHM",
         "mongolia": "MNG", "micronesia": "FSM", "federated states of micronesia": "FSM", "the gambia": "GMB", "gambia": "GMB",
         "democratic republic of the congo": "COD", "congo": "COG", "cabo verde": "CPV", "cape verde": "CPV", "comoros": "COM",
         "moldova": "MDA", "republic of moldova": "MDA", "laos": "LAO", "netherlands antilles": "ANT"}


def get(url, timeout=120):
    last = None
    for i in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(5 * (i + 1))
    raise RuntimeError(f"{url}: {last}")


def text(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def vessel(page):
    rec = {}
    # The overview: a definition list of label and value.
    for dt, dd in re.findall(r"<dt[^>]*>(.*?)</dt>\s*<dd[^>]*>(.*?)</dd>", page, re.S | re.I):
        k, v = text(dt).rstrip(":"), text(dd)
        if k:
            rec[k] = v
    # Each history: a heading, then a table.
    # Round 123b: a heading closes with its own level (the page's h1 ran on to
    # a later h4 and swallowed the whole page as one "heading").
    for _lv, head, table in re.findall(r"<h(\d)[^>]*>((?:(?!<h\d).)*?)</h\1>\s*(?:<[^t][^>]*>\s*)*<table[^>]*>(.*?)</table>", page, re.S | re.I):
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.S | re.I)
        if not rows:
            continue
        cols = [text(c) for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", rows[0], re.S | re.I)]
        body = [[text(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", r, re.S | re.I)] for r in rows[1:]]
        rec[text(head)] = [dict(zip(cols, b)) for b in body if any(b)]
    # Round 123b: label/value pairs written as rows of two cells or as
    # "Label: value" lines, when the page has no definition list.
    if not any(k in rec for k in ("Current Flag", "Flag")):
        for a, b in re.findall(r"<tr[^>]*>\s*<t[hd][^>]*>(.*?)</t[hd]>\s*<td[^>]*>(.*?)</td>\s*</tr>", page, re.S | re.I):
            k, v = text(a).rstrip(":"), text(b)
            if k and len(k) < 60 and k not in rec and not JUNK.match(k):
                rec[k] = v
        for a, b in re.findall(r"<(?:label|span|strong|b|div)[^>]*>\s*([A-Z][A-Za-z /()]{1,40}):?\s*</(?:label|span|strong|b|div)>\s*<(?:span|div|p)[^>]*>(.*?)</(?:span|div|p)>", page, re.S):
            k, v = text(a).rstrip(":"), text(b)
            if k and k not in rec and v:
                rec[k] = v
    return rec


def from_download():
    """Round 123b: TMT's own spreadsheet of every vessel, if the owner has
    downloaded it (iuu-vessels.org/Home/Download asks a reason first) and put
    it in iuu/download/. Every column kept."""
    files = sorted(OUT.glob("download/*.xls*"))
    if not files:
        return None
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "openpyxl"], check=True)
    import openpyxl
    wb = openpyxl.load_workbook(files[-1], data_only=True)
    ws = max(wb.worksheets, key=lambda w: w.max_row)
    rows = list(ws.iter_rows(values_only=True))
    hi = next(i for i, r in enumerate(rows[:20]) if sum(1 for c in r if c not in (None, "")) >= 4)
    head = [str(c or f"column {k + 1}").strip() for k, c in enumerate(rows[hi])]
    out = []
    for r in rows[hi + 1:]:
        rec = {head[k]: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in enumerate(r) if k < len(head) and v not in (None, "")}
        if rec:
            fk = next((h for h in head if re.search(r"current flag|^flag", h, re.I)), None)
            if fk and rec.get(fk) and "Current Flag" not in rec:
                rec["Current Flag"] = str(rec[fk])
            nk = next((h for h in head if re.search(r"^(vessel )?name", h, re.I)), None)
            if nk and rec.get(nk) and "Name" not in rec:
                rec["Name"] = str(rec[nk])
            pk = next((h for h in head if re.search(r"position", h, re.I)), None)
            if pk and rec.get(pk):
                rec["Last known position"] = str(rec[pk])
            rec["page"] = files[-1].name
            out.append(rec)
    print(f"iuu_vessels: {len(out)} vessels from {files[-1]}", flush=True)
    return out


def position(s):
    """A last known position as the page writes it, read as decimal degrees if it can be."""
    s = (s or "").strip()
    if not s:
        return None
    nums = re.findall(r"(-?\d+(?:\.\d+)?)\s*°?\s*(?:(\d+(?:\.\d+)?)\s*['′])?\s*([NSEW])?", s, re.I)
    vals = []
    for d, m, h in nums:
        v = float(d) + (float(m) / 60 if m else 0)
        if h and h.upper() in "SW":
            v = -abs(v)
        vals.append((v, (h or "").upper()))
    if len(vals) < 2:
        return None
    (a, ha), (b, hb) = vals[0], vals[1]
    lat, lon = (b, a) if ha in "EW" and ha else (a, b)
    return (lon, lat) if -90 <= lat <= 90 and -180 <= lon <= 180 else None


# Round 129b: rows of the history tables were read as labels ("2014-11",
# "From To Name 2021-05-07"), giving hundreds of junk fields; they are dropped
# (the histories are kept whole under their own headings).
JUNK = re.compile(r"^(\d{4}(-\d\d){0,2}|From To\b.*)$")


def place_named(s, cache):
    """A last known position written as a place ("Yantai, China / Bohai Sea"):
    the port first, else the sea, by OpenStreetMap's Nominatim. Not a reported
    coordinate; the box says so."""
    for part in [p.strip() for p in s.split("/") if p.strip()]:
        if part in cache:
            if cache[part]:
                return cache[part], part
            continue
        url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode({"q": part, "format": "json", "limit": 1})
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=NOMI), timeout=60) as r:
                j = json.loads(r.read())
            cache[part] = [float(j[0]["lon"]), float(j[0]["lat"])] if j else None
        except Exception as e:  # noqa: BLE001
            print(f"  Nominatim {part}: {e}", flush=True)
            continue
        time.sleep(1.2)
        if cache[part]:
            return cache[part], part
    return None, None


def main():
    stamp = OUT / "build.json"
    if stamp.exists() and datetime.date.today().weekday() != 0 and os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
        print("iuu_vessels: weekly; not Monday")
        return
    OUT.mkdir(exist_ok=True)
    vessels = from_download()
    if vessels is not None:
        return finish(vessels, set(k for v in vessels for k in v), stamp)
    search = get(f"{BASE}/Home/Search")
    links = sorted(set(re.findall(r'href="((?:https?://(?:www\.)?iuu-vessels\.org)?/Vessel/GetVessel/[0-9a-f-]+)"', search, re.I)))
    print(f"iuu_vessels: {len(links)} vessels listed", flush=True)
    if not links:
        (OUT / "search_page.html").write_text(search)
        raise SystemExit("iuu_vessels: no vessel links on the search page; the page is saved as iuu/search_page.html")
    vessels, fields = [], set()
    for i, href in enumerate(links):
        url = href if href.startswith("http") else BASE + href
        try:
            page = get(url)
            if i == 0:
                (OUT / "sample_page.html").write_text(page)
            rec = vessel(page)
        except Exception as e:  # noqa: BLE001
            rec = {"error": str(e)}
        rec["page"] = url
        fields.update(rec)
        vessels.append(rec)
        if i % 50 == 49:
            print(f"  {i + 1} of {len(links)} read", flush=True)
        time.sleep(0.4)
    finish(vessels, fields, stamp)


def finish(vessels, fields, stamp):
    (OUT / "vessels.json").write_text(json.dumps(vessels, indent=1, ensure_ascii=False))
    names = {}
    try:
        for f in json.loads(get(NE, 300))["features"]:
            p = f["properties"]
            iso = p.get("ADM0_A3") if p.get("ISO_A3") in (None, "-99") else p["ISO_A3"]
            for k in ("NAME", "NAME_LONG", "ADMIN", "FORMAL_EN", "NAME_SORT"):
                if p.get(k):
                    names[str(p[k]).strip().lower()] = iso
    except Exception as e:  # noqa: BLE001
        print(f"iuu_vessels: Natural Earth's names could not be read ({e}); only the list above is used", flush=True)
    names.update(ALIAS)
    flags, unmatched, unknown = {}, {}, 0
    for v in vessels:
        f = (v.get("Current Flag") or "").strip()
        if not f or f.lower() in ("unknown", "n/a", "-", "none"):
            unknown += 1
            continue
        iso = names.get(f.lower())
        if not iso:
            unmatched[f] = unmatched.get(f, 0) + 1
            continue
        r = flags.setdefault(iso, {"value": 0, "x_flag as the list writes it": f, "x_vessels": []})
        r["value"] += 1
        r["x_vessels"].append(v.get("Name") or v.get("RFMO Vessel Name") or v["page"])
    for r in flags.values():
        r["x_vessels"] = "; ".join(sorted(r["x_vessels"]))
    (OUT / "flags.json").write_text(json.dumps(flags, indent=1, ensure_ascii=False))
    for v in vessels:
        for k in [k for k in v if JUNK.match(str(k))]:
            del v[k]
    cache_f = OUT / "places.json"
    try:
        cache = json.loads(cache_f.read_text())
    except Exception:  # noqa: BLE001
        cache = {}
    pts, unread = [], []
    for v in vessels:
        lkp = (v.get("Last known position") or "").strip()
        at, how = position(lkp), "the coordinates the list gives"
        if not at and lkp:
            at, part = place_named(lkp, cache)
            how = f"the place the list names, {part}, by OpenStreetMap's Nominatim (not a reported coordinate)" if at else how
        if at:
            props = {k: (json.dumps(x, ensure_ascii=False) if isinstance(x, (list, dict)) else x) for k, x in v.items()}
            props["placed at"] = how
            pts.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(at[0], 4), round(at[1], 4)]}, "properties": props})
        elif lkp:
            unread.append(lkp)
    cache_f.write_text(json.dumps(cache, ensure_ascii=False))
    (OUT / "positions.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": pts}, ensure_ascii=False))
    stamp.write_text(json.dumps({"vessels": len(vessels), "flags": len(flags), "flag_unknown": unknown, "flags_not_matched": unmatched,
                                 "positions": len(pts), "positions_not_read": unread[:50], "fields": sorted({k for v in vessels for k in v}),
                                 "date": datetime.date.today().isoformat()}, indent=1, ensure_ascii=False))
    print(f"iuu_vessels: {len(vessels)} vessels, {len(flags)} flags, {unknown} with no known flag, {len(pts)} positions; not matched {unmatched}")


if __name__ == "__main__":
    main()
