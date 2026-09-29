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
import datetime, html, json, os, pathlib, re, sys, time, urllib.request

BASE = "https://iuu-vessels.org"
UA = {"User-Agent": "Mozilla/5.0 (Culprits atlas build; welcometoyourgalaxy@gmail.com)"}
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
    for head, table in re.findall(r"<h\d[^>]*>(.*?)</h\d>\s*(?:<[^t][^>]*>\s*)*<table[^>]*>(.*?)</table>", page, re.S | re.I):
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.S | re.I)
        if not rows:
            continue
        cols = [text(c) for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", rows[0], re.S | re.I)]
        body = [[text(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", r, re.S | re.I)] for r in rows[1:]]
        rec[text(head)] = [dict(zip(cols, b)) for b in body if any(b)]
    return rec


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


def main():
    stamp = OUT / "build.json"
    if stamp.exists() and datetime.date.today().weekday() != 0 and os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
        print("iuu_vessels: weekly; not Monday")
        return
    OUT.mkdir(exist_ok=True)
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
            rec = vessel(get(url))
        except Exception as e:  # noqa: BLE001
            rec = {"error": str(e)}
        rec["page"] = url
        fields.update(rec)
        vessels.append(rec)
        if i % 50 == 49:
            print(f"  {i + 1} of {len(links)} read", flush=True)
        time.sleep(0.4)
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
    pts, unread = [], []
    for v in vessels:
        at = position(v.get("Last known position"))
        if at:
            pts.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(at[0], 4), round(at[1], 4)]},
                        "properties": {k: (json.dumps(x, ensure_ascii=False) if isinstance(x, (list, dict)) else x) for k, x in v.items()}})
        elif (v.get("Last known position") or "").strip():
            unread.append(v["Last known position"])
    (OUT / "positions.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": pts}, ensure_ascii=False))
    stamp.write_text(json.dumps({"vessels": len(vessels), "flags": len(flags), "flag_unknown": unknown, "flags_not_matched": unmatched,
                                 "positions": len(pts), "positions_not_read": unread[:50], "fields": sorted(fields),
                                 "date": datetime.date.today().isoformat()}, indent=1, ensure_ascii=False))
    print(f"iuu_vessels: {len(vessels)} vessels, {len(flags)} flags, {unknown} with no known flag, {len(pts)} positions; not matched {unmatched}")


if __name__ == "__main__":
    main()
