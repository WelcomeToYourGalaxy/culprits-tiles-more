#!/usr/bin/env python3
"""
Who owns the energy and heavy-industry assets: Global Energy Monitor's Global
Energy Ownership Tracker (round 216o, asked 16 October 2026; GEM's project
manager Anna Mowat pointed to it on 16 October, for the assets not yet
operating that Climate TRACE leaves out).

Licence: CC BY 4.0. Credit: "Global Energy Monitor, Global Energy Ownership
Tracker, <release>". GEM notes that Chinese ownership has not been updated
since early 2023; the layer notes say so.

GEM gives the tracker only through its download form. The workbook (55 MB in
September 2026) is too big for GitHub's web upload, so it can be put in
gem/ownership/download/ either as it comes or as the compressed CSV copy of
every sheet (one .csv.gz per sheet, or a zip of them); this script reads
whichever is there, every sheet, every row, every column.

What it writes, in gem/ownership/:

  parents.geojson    every parent GEM names in its sector sheets (coal, oil
                     and gas and bioenergy plants, coal and iron ore mines,
                     gas and oil pipelines, steel and cement plants): placed
                     at its headquarters country's capital (or registration
                     country's, where no headquarters is given), spread so each
                     can be clicked; GEM gives the country, not the address.
                     For each sector: the units it holds, their capacity
                     counted by its share, split into operating, being
                     developed (announced, pre-permit, permitted,
                     pre-construction, construction) and the rest (shelved,
                     cancelled, mothballed, retired), with the unit GEM uses.
  entities.geojson   every entity in the tracker (companies, states, state
                     bodies, arrangements, people), at its country's capital
                     the same way, with who owns it and what it owns (each with
                     its percentage, as GEM gives it) and the assets it owns
                     directly.
  build.json         the release, sheets and counts read, and every entity
                     not placed (no country, or one not matched to a code).

Nothing is estimated: a share GEM does not give is left out of the
share-weighted figures and counted apart.
"""
import csv, datetime, gzip, hashlib, io, json, math, pathlib, re, sys, tempfile, zipfile
from collections import defaultdict

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
SRC = pathlib.Path("gem/ownership/download")
OUT = pathlib.Path("gem/ownership")
STAMP = OUT / "build.json"
DEVELOPING = re.compile(r"^(announced|pre-permit|permitted|pre-construction|construction|in development|proposed)", re.I)
OPERATING = re.compile(r"^operating", re.I)
SECTOR_SHEET = re.compile(r"ownership$", re.I)
# GEM's country names that pycountry does not read as written.
NAMES = {"Russia": "RUS", "Iran": "IRN", "Syria": "SYR", "South Korea": "KOR", "North Korea": "PRK", "Laos": "LAO", "Vietnam": "VNM",
         "Taiwan": "TWN", "Bolivia": "BOL", "Venezuela": "VEN", "Tanzania": "TZA", "Moldova": "MDA", "Turkey": "TUR", "Türkiye": "TUR",
         "Czech Republic": "CZE", "Czechia": "CZE", "DR Congo": "COD", "Democratic Republic of the Congo": "COD", "Republic of the Congo": "COG",
         "Congo": "COG", "Ivory Coast": "CIV", "Côte d'Ivoire": "CIV", "Brunei": "BRN",
         "United States": "USA", "United Kingdom": "GBR", "Micronesia": "FSM", "Cape Verde": "CPV", "Eswatini": "SWZ", "Swaziland": "SWZ",
         "Macedonia": "MKD", "North Macedonia": "MKD", "Burma": "MMR", "Myanmar": "MMR", "Hong Kong": "HKG", "Macau": "MAC", "Macao": "MAC",
         "Curacao": "CUW", "Curaçao": "CUW", "Bonaire, Sint Eustatius, and Saba": "BES", "Virgin Islands (U.K.)": "VGB",
         "British Virgin Islands": "VGB", "Virgin Islands (U.S.)": "VIR", "Saint Kitts and Nevis": "KNA", "East Timor": "TLS", "Timor-Leste": "TLS",
         "Virgin Islands (British)": "VGB", "Virgin Islands (U.S)": "VIR", "Palestine": "PSX", "Kosovo": "KOS", "The Gambia": "GMB", "Gambia": "GMB", "The Bahamas": "BHS", "Bahamas": "BHS", "Sao Tome and Principe": "STP", "Vatican City": "VAT"}


def files():
    """Every sheet in the download folder, as (name, rows): workbooks, CSVs (also gzipped), and zips of either."""
    def from_bytes(name, data):
        low = name.lower()
        if low.endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                for n in sorted(z.namelist()):
                    if not n.endswith("/"):
                        yield from from_bytes(n, z.read(n))
        elif low.endswith(".csv.gz"):
            yield pathlib.Path(name[:-7]).name, list(csv.reader(io.StringIO(gzip.decompress(data).decode("utf-8-sig"))))
        elif low.endswith(".csv"):
            yield pathlib.Path(name[:-4]).name, list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))
        elif low.endswith((".xlsx", ".xlsm")):
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
            for ws in wb.worksheets:
                yield ws.title, [["" if v is None else v for v in r] for r in ws.iter_rows(values_only=True)]
    for p in sorted(SRC.rglob("*")):
        if p.is_file() and p.name.lower() != "readme.md":
            yield from from_bytes(p.name, p.read_bytes())


def sheet_key(name):
    return re.sub(r"[^a-z0-9]+", " ", str(name).lower()).strip()


def table(rows):
    """Rows as dicts under the first row that has several named columns."""
    for i, r in enumerate(rows[:10]):
        named = [c for c in r if str(c).strip()]
        if len(named) >= 3:
            head = [str(c).strip() or f"column {j + 1}" for j, c in enumerate(r)]
            out = []
            for x in rows[i + 1:]:
                if any(str(v).strip() for v in x):
                    out.append({h: ("" if j >= len(x) else x[j]) for j, h in enumerate(head) if not h.startswith("column ")})
            return head, out
    return [], []


def num(v):
    try:
        f = float(str(v).replace(",", "").strip())
        return f if math.isfinite(f) else None
    except ValueError:
        return None


def text(v):
    return re.sub(r"\s+", " ", str(v if v is not None else "")).strip()


def iso3(name, cache={}):
    name = text(name)
    if not name:
        return None
    if name in cache:
        return cache[name]
    code = NAMES.get(name)
    if not code:
        try:
            import pycountry
            c = pycountry.countries.lookup(name)
            code = c.alpha_3
        except Exception:  # noqa: BLE001
            try:
                import pycountry
                hits = pycountry.countries.search_fuzzy(name)
                code = hits[0].alpha_3 if len(hits) == 1 else None
            except Exception:  # noqa: BLE001
                code = None
    cache[name] = code
    return code


def capacity_column(head):
    """The sector sheet's capacity column (the first that says capacity, else production), and its unit as GEM writes it."""
    for pat in (r"capacity", r"production"):
        for h in head:
            if re.search(pat, h, re.I):
                m = re.search(r"\(([^)]+)\)", h)
                unit = m.group(1) if m else re.sub(r"(?i).*capacity", "", h).strip() or h
                return h, unit
    return None, None


def clip(t, n=1400, more=""):
    return t if len(t) <= n else t[:n].rsplit("; ", 1)[0] + f"; ... ({more})"


def main():
    if SRC.is_file():          # an empty placeholder file where the folder belongs
        SRC.unlink()
    SRC.mkdir(parents=True, exist_ok=True)
    readme = SRC / "README.md"
    if not readme.exists():
        readme.write_text("Upload Global Energy Monitor's Global Energy Ownership Tracker here: the workbook as it comes, "
                          "or a zip of its sheets as compressed CSVs (the workbook is too big for GitHub's web upload).\n")
    src = [p for p in sorted(SRC.rglob("*")) if p.is_file() and p.name.lower() != "readme.md"]
    if not src:
        print("gem_ownership: nothing in gem/ownership/download yet; the rows say they are not built")
        return
    h = hashlib.sha256()
    for p in src:
        h.update(p.name.encode()); h.update(p.read_bytes())
    digest = h.hexdigest()
    if STAMP.exists() and (OUT / "parents.geojson").exists():
        try:
            if json.loads(STAMP.read_text()).get("sha256") == digest:
                print("gem_ownership: download unchanged; the copy stands")
                return
        except ValueError:
            pass
    try:
        import pycountry  # noqa: F401
    except ImportError:
        import subprocess
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "pycountry", "openpyxl"], check=False)
    sheets, about = {}, []
    for name, rows in files():
        k = sheet_key(name)
        if k == "about":
            about = [" ".join(text(c) for c in r if text(c)) for r in rows]
            continue
        sheets[k] = (name, *table(rows))
    release = next((a for a in about if re.match(r"Global Energy Ownership Tracker\s*-", a)), "Global Energy Ownership Tracker")
    cite = f"Global Energy Monitor, {release.replace(' - ', ', ')} (CC BY 4.0)"
    ents_t = next((v for k, v in sheets.items() if k == "all entities"), None)
    if not ents_t:
        sys.exit("gem_ownership: no 'All Entities' sheet was found in the download")
    ents = {text(r.get("Entity ID")): r for r in ents_t[2] if text(r.get("Entity ID"))}
    links = next((v for k, v in sheets.items() if k == "entity ownership"), (None, [], []))[2]
    direct = next((v for k, v in sheets.items() if k == "asset ownership"), (None, [], []))[2]

    def ename(e):
        x = ents.get(e) or {}
        return text(x.get("Name")) or text(x.get("Full Name")) or e

    # ---------- parents, from every sector sheet ----------
    parents = defaultdict(lambda: {"units": 0, "sectors": defaultdict(lambda: {"units": 0, "unit": "", "op": 0.0, "dev": 0.0, "other": 0.0,
                                                                            "no share": 0, "no capacity": 0, "status": defaultdict(int)}),
                                   "lines": [], "names": set(), "hq": "", "reg": ""})
    sector_counts = {}
    for k, (name, head, rows) in sheets.items():
        if not SECTOR_SHEET.search(k) or k in ("entity ownership", "asset ownership"):
            continue
        # The sheet's own name (a CSV copy writes it with _ for spaces and "and" for &).
        sector = re.sub(r"(?i)\s*ownership$", "", re.sub(r"_+", " ", name).replace(" and NGL", " & NGL")).strip()
        capc, unit = capacity_column(head)
        statc = next((c for c in head if re.search(r"status", c, re.I)), None)
        sector_counts[sector] = len(rows)
        for r in rows:
            pid = text(r.get("Parent GEM Entity ID"))
            if not pid:
                continue
            p = parents[pid]
            p["names"].add(text(r.get("Parent")))
            p["hq"] = p["hq"] or text(r.get("Parent Headquarters Country"))
            p["reg"] = p["reg"] or text(r.get("Parent Registration Country"))
            s = p["sectors"][sector]
            s["unit"] = unit or ""
            s["units"] += 1
            p["units"] += 1
            st = text(r.get(statc)) if statc else ""
            s["status"][st or "status not given"] += 1
            share, cap = num(r.get("Share")), num(r.get(capc)) if capc else None
            bucket = "op" if OPERATING.match(st) else "dev" if DEVELOPING.match(st) else "other"
            if cap is None:
                s["no capacity"] += 1
            elif share is None:
                s["no share"] += 1
            else:
                s[bucket] += cap * share / 100
            p["lines"].append((cap * (share or 0) / 100 if cap is not None else 0,
                               f"{text(r.get('Project'))} ({sector}, {st or 'status not given'}"
                               + (f", {cap:g} {unit}" if cap is not None else "") + f"): {share:g}%" if share is not None else
                               f"{text(r.get('Project'))} ({sector}, {st or 'status not given'}): share not given",
                               text(r.get("Ownership Path"))))
    from forest500_map import capitals
    caps = capitals()
    spin, unplaced = {}, []

    def place(code):
        cap = caps.get(code)
        if not cap:
            return None, None
        i = spin[code] = spin.get(code, -1) + 1
        ang, rad = math.radians(137.508 * i), 0.12 * math.sqrt(i)
        lon = cap[0] + rad * math.cos(ang) / max(0.3, math.cos(math.radians(cap[1])))
        lat = max(-85, min(85, cap[1] + rad * math.sin(ang)))
        return [round(lon, 5), round(lat, 5)], cap

    def placeable(hq, reg):
        """The headquarters country if it can be placed, else the registration country."""
        for c, w in ((iso3(hq), "headquarters"), (iso3(reg), "registration")):
            if c and c in caps:
                return c, w
        return None, None

    def fmt(v):
        return f"{v:,.4g}" if v and v < 1000 else f"{v:,.0f}"

    order = sorted(parents, key=lambda k: -parents[k]["units"])
    feats = []
    for pid in order:
        p, x = parents[pid], ents.get(pid) or {}
        hq = text(x.get("Headquarters Country")) or p["hq"]
        reg = text(x.get("Registration Country")) or p["reg"]
        row = {"parent": ename(pid) if pid in ents else sorted(p["names"])[0], "GEM entity id": pid,
               "kind": text(x.get("Entity Type")), "legal form": text(x.get("Legal Entity Type")), "publicly listed": text(x.get("PubliclyListed")),
               "headquarters country": hq, "registration country": reg, "home page": text(x.get("Home Page")),
               "units held (power units, mines, pipelines, plants)": p["units"], "sectors": "; ".join(sorted(p["sectors"]))}
        dev_total = 0
        for sec, s in sorted(p["sectors"].items()):
            u = s["unit"]
            row[f"{sec}: units"] = s["units"]
            row[f"{sec}: operating, by its shares ({u})"] = round(s["op"], 3)
            row[f"{sec}: being developed, by its shares ({u})"] = round(s["dev"], 3)
            row[f"{sec}: shelved, cancelled, mothballed or retired, by its shares ({u})"] = round(s["other"], 3)
            row[f"{sec}: units by status"] = "; ".join(f"{k}: {v}" for k, v in sorted(s["status"].items(), key=lambda kv: -kv[1]))
            if s["no share"] or s["no capacity"]:
                row[f"{sec}: not in the figures"] = f"{s['no share']} units with no share given, {s['no capacity']} with no capacity given"
            dev_total += sum(n for st, n in s["status"].items() if DEVELOPING.match(st))
        row["units being developed (announced to construction)"] = dev_total
        p["lines"].sort(key=lambda t: -t[0])
        row["units and shares"] = clip("; ".join(l_ for _, l_, _ in p["lines"]), 1200, f"{len(p['lines'])} units in all, each with its ownership path, in GEM's sector sheets")
        row["an ownership path"] = p["lines"][0][2] if p["lines"] else ""
        code, where = placeable(hq, reg)
        at, cap = place(code) if code else (None, None)
        if not at:
            unplaced.append({"parent": row["parent"], "headquarters": hq, "registration": reg})
            continue
        row["placed at"] = (f"the capital of its {where} country ({cap[2]})" if cap[3] == "capital" else f"{cap[2]}, in its {where} country") + \
            "; GEM gives the country, not the address. Spread so each can be clicked."
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": at}, "properties": row})
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "parents.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False))

    # ---------- every entity, with who owns it and what it owns ----------
    owners_of, owns = defaultdict(list), defaultdict(list)
    for r in links:
        s, o = text(r.get("Subject Entity ID")), text(r.get("Interested Party ID"))
        if not s or not o:
            continue
        pct = num(r.get("% Share of Ownership"))
        imp = text(r.get("Share Imputed?"))
        tag = (f"{pct:g}%" if pct is not None else "share not given") + (" (share imputed by GEM)" if imp.lower() in ("true", "yes", "1") else "")
        owners_of[s].append(f"{text(r.get('Interested Party Name')) or ename(o)} ({tag})")
        owns[o].append(f"{text(r.get('Subject Entity Name')) or ename(s)} ({tag})")
    assets_of = defaultdict(list)
    for r in direct:
        e = text(r.get("Immediate Owner Entity ID"))
        if not e:
            continue
        pct = num(r.get("% Share of Ownership"))
        assets_of[e].append(f"{text(r.get('Asset Name'))} ({text(r.get('Asset Type'))}, " + (f"{pct:g}%" if pct is not None else "share not given") + ")")
    spin.clear()
    efeats, e_unplaced = [], []
    for eid, x in ents.items():
        hq, reg = text(x.get("Headquarters Country")), text(x.get("Registration Country"))
        props = {k: text(v) for k, v in x.items() if k and text(v) and text(v) != "not found"}
        props["owned by"] = clip("; ".join(owners_of.get(eid, [])), 500, f"{len(owners_of.get(eid, []))} in all, in GEM's Entity Ownership sheet")
        props["owns (companies and bodies)"] = clip("; ".join(owns.get(eid, [])), 500, f"{len(owns.get(eid, []))} in all, in GEM's Entity Ownership sheet")
        props["owns directly (assets)"] = clip("; ".join(assets_of.get(eid, [])), 500, f"{len(assets_of.get(eid, []))} in all, in GEM's Asset Ownership sheet")
        props["owners"], props["companies and bodies it owns"], props["assets it owns directly"] = len(owners_of.get(eid, [])), len(owns.get(eid, [])), len(assets_of.get(eid, []))
        props["a parent in GEM's sense"] = "yes" if eid in parents else "no"
        code, where = placeable(hq, reg)
        at, cap = place(code) if code else (None, None)
        if not at:
            e_unplaced.append(eid)
            continue
        props["placed at"] = (f"the capital of its {where} country ({cap[2]})" if cap[3] == "capital" else f"{cap[2]}, in its {where} country") + \
            "; GEM gives the country, not the address. Spread so each can be clicked."
        efeats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": at}, "properties": props})
    (OUT / "entities.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": efeats}, ensure_ascii=False))
    status = {"sha256": digest, "read": datetime.date.today().isoformat(), "release": release, "cite": cite,
              "files": [p.name for p in src], "sheets": {k: len(v[2]) for k, v in sheets.items()}, "sector rows": sector_counts,
              "parents": len(parents), "parents placed": len(feats), "parents not placed": unplaced,
              "entities": len(ents), "entities placed": len(efeats), "entities not placed, count": len(e_unplaced),
              "entities not placed": [{"entity": ename(e), "id": e, "headquarters": text(ents[e].get("Headquarters Country")),
                                       "registration": text(ents[e].get("Registration Country"))} for e in e_unplaced[:2000]]}
    STAMP.write_text(json.dumps(status, indent=1, ensure_ascii=False))
    print(f"gem_ownership: {len(parents)} parents, {len(feats)} placed; {len(ents)} entities, {len(efeats)} placed; from {release}")


if __name__ == "__main__":
    main()
