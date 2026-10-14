#!/usr/bin/env python3
"""
Who owns the emissions: Climate TRACE's full ownership chains (round 192o,
asked 12 October; the Climate TRACE Coalition sent the files on 12 October).

Climate TRACE's ownership tables (the 7 October 2026 release, CC BY 4.0), kept
in ct_ownership/ and read again from Climate TRACE's storage when it answers:

  entities.csv              every owner: name, kind (company, state, state
                            body, person ...), headquarters and registration
                            country, identifiers, GEM parents
  asset_relationships.csv   each emitting site and the owner(s) Climate TRACE
                            names for it (no share is given at this step)
  entity_relationships.csv  who owns whom, with the percentage where given,
                            and the sources

Each site's emissions come from Climate TRACE's own sector packages
(latest/sector_packages/co2e_100yr/<sector>.zip): the latest full year of
each owned site, in tonnes of CO2-equivalent (100-year). A sector is read
once a month, one or more per run as time allows; what has been read is
kept in ct_ownership/emissions_<sector>.json.

Every chain is followed from each site up to the owners at the top (owners
Climate TRACE lists no owner for). Nothing is filled in:
  - Climate TRACE gives no share between a site and its named owner, so the
    site is counted whole at that step;
  - between owners its percentage is multiplied along the chain; where an
    owner is reached by several chains to one site it is counted once, at
    the largest share any chain gives;
  - where any step of a chain has no percentage, that site's emissions are
    not divided: they are shown apart, as emissions through chains of
    unknown share;
  - a third figure, every site it sits above, not divided at all, is kept
    beside them.

  ct_ownership/top_owners.geojson   each owner at the top of a chain, at its
                                    headquarters country's capital, spread
  ct_ownership/top_owners.json      all of them, ranked, with every site
  ct_ownership/sites.geojson        every owned site Climate TRACE places,
                                    with its emissions and every chain
  ct_ownership/build.json

Daily with the refresh (it does nothing new until a month has passed or the
tables change), or by hand.
"""
import csv, datetime, io, json, math, os, pathlib, sys, tempfile, time, urllib.request, zipfile
from collections import defaultdict

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
START = time.time()
NO_NEW_SECTOR_AFTER = 80 * 60
DIR = pathlib.Path("ct_ownership")
REMOTE = "https://storage.googleapis.com/climate_trace/ownership/"
TABLES = {"entities.csv": "ownership_all_entities_071026.csv",
          "asset_relationships.csv": "ownership_all_entity_asset_relationships_071026.csv",
          "entity_relationships.csv": "ownership_all_entity_relationships_071026.csv"}
PACKAGE = "https://downloads.climatetrace.org/latest/sector_packages/co2e_100yr/{}.zip"
SECTOR = {"power": "power", "fossil-fuel-operations": "fossil_fuel_operations", "agriculture": "agriculture",
          "manufacturing": "manufacturing", "mineral-extraction": "mineral_extraction"}
MONTH_DAYS = 30
UA = {"User-Agent": "WelcomeToYourGalaxy Culprits map (welcometoyourgalaxy@gmail.com)"}
CITE = "Climate TRACE (CC BY 4.0): ownership tables of 7 October 2026 and its sector emissions packages (CO2e, 100-year)"


def get(url, timeout=300):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read()


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def tables(status):
    """The three tables: Climate TRACE's storage when it answers, else the copies here."""
    out = {}
    for local, remote in TABLES.items():
        path = DIR / local
        try:
            body = get(REMOTE + remote, 300)
            if body and (not path.exists() or path.read_bytes() != body):
                path.write_bytes(body)
            status["tables"][local] = f"read from {REMOTE}{remote}"
        except Exception as e:  # noqa: BLE001
            status["tables"][local] = f"the copy here ({type(e).__name__} from Climate TRACE's storage)"
        with open(path, encoding="utf-8-sig", newline="") as f:
            out[local] = [r for r in csv.DictReader(f)]
    return out


def read_package(sector, wanted, status):
    """One sector package -> {source_id: site} for the owned sites, the latest full year."""
    url = PACKAGE.format(sector)
    tmp = pathlib.Path(tempfile.mkdtemp()) / f"{sector}.zip"
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=1800) as r, open(tmp, "wb") as f:
        release = r.headers.get("Last-Modified") or r.headers.get("ETag")
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    years = defaultdict(lambda: defaultdict(lambda: [0.0, 0]))   # sid -> year -> [tonnes, months]
    info, cols_seen, files_used = {}, set(), []
    with zipfile.ZipFile(tmp) as z:
        for name in z.namelist():
            if not name.lower().endswith(".csv"):
                continue
            with z.open(name) as fh:
                rd = csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8-sig"))
                cols = {c.strip().lower() for c in (rd.fieldnames or [])}
                if not ({"source_id", "emissions_quantity"} <= cols):
                    continue
                files_used.append(name)
                cols_seen |= cols
                for row in rd:
                    sid = str(row.get("source_id") or "").strip()
                    if sid not in wanted:
                        continue
                    gas = str(row.get("gas") or "").lower()
                    if gas and gas != "co2e_100yr":
                        continue
                    q = num(row.get("emissions_quantity"))
                    st, en = str(row.get("start_time") or ""), str(row.get("end_time") or "")
                    if q is None or len(st) < 4:
                        continue
                    y = int(st[:4])
                    months = 12 if (st[5:10] == "01-01" and en[5:10] in ("12-31", "01-01") and en[:4] in (st[:4], str(y + 1))) else 1
                    years[sid][y][0] += q
                    years[sid][y][1] += months
                    if sid not in info:
                        info[sid] = {"name": row.get("source_name"), "lat": num(row.get("lat")), "lon": num(row.get("lon")),
                                     "country": row.get("iso3_country"), "subsector": row.get("subsector"), "sector": row.get("sector") or sector}
    tmp.unlink()
    out = {}
    for sid, ys in years.items():
        full = [y for y, (_, m) in ys.items() if m >= 12]
        y = max(full) if full else max(ys)
        out[sid] = dict(info[sid], year=y, tonnes=round(ys[y][0], 1), full_year=bool(full))
    status["sectors"][sector] = {"release": release, "files used": len(files_used), "owned sites found": len(out),
                                 "owned sites asked": len(wanted), "columns": sorted(cols_seen)[:40]}
    return out, release


def emissions(assets, status):
    """Every owned site's emissions, sector by sector, from the cache or the packages."""
    by_sector = defaultdict(set)
    for r in assets:
        sec = SECTOR.get(str(r.get("source_sector") or "").strip().lower())
        if sec and r.get("source_id"):
            by_sector[sec].add(str(r["source_id"]).strip())
    sites = {}
    for sec in sorted(by_sector, key=lambda s: len(by_sector[s])):
        cache = DIR / f"emissions_{sec}.json"
        old = json.loads(cache.read_text()) if cache.exists() else {}
        fresh = old.get("read") and (datetime.date.today() - datetime.date.fromisoformat(old["read"])).days < MONTH_DAYS
        if not fresh and time.time() - START < NO_NEW_SECTOR_AFTER:
            try:
                got, release = read_package(sec, by_sector[sec], status)
                old = {"read": datetime.date.today().isoformat(), "release": release, "sites": got}
                cache.write_text(json.dumps(old, ensure_ascii=False))
            except Exception as e:  # noqa: BLE001
                status["sectors"][sec] = dict(status["sectors"].get(sec, {}), refused=f"{type(e).__name__}: {e}"[:300])
                print(f"::warning::ct_ownership: {sec}: {e}", flush=True)
        elif not fresh:
            status["waiting"].append(sec)
        if old.get("sites"):
            status["sectors"].setdefault(sec, {})["emissions as of"] = old.get("read")
            sites.update(old["sites"])
    return sites


def clip(t, n=1500):
    """A box holds the first 1,500 characters; every chain is in chains.json."""
    return t if len(t) <= n else t[:n].rsplit(" | ", 1)[0] + " | ... (every chain in ct_ownership/chains.json)"


def main():
    DIR.mkdir(exist_ok=True)
    status = {"read": datetime.date.today().isoformat(), "source": CITE, "tables": {}, "sectors": {}, "waiting": []}
    t = tables(status)
    ents = {r["Entity ID"]: r for r in t["entities.csv"] if r.get("Entity ID")}
    assets = [r for r in t["asset_relationships.csv"] if r.get("source_id")]
    owners_of = defaultdict(list)
    for r in t["entity_relationships.csv"]:
        s, o = r.get("subject_entity_id"), r.get("owner_entity_id")
        if s and o and s != o:
            owners_of[s].append((o, num(r.get("percent_of_ownership")), r.get("data_source_url") or ""))
    sites = emissions(assets, status)
    site_owners = defaultdict(list)
    site_meta = {}
    for r in assets:
        sid = str(r["source_id"]).strip()
        site_owners[sid].append(r.get("immediate_source_owner_entity_id"))
        site_meta.setdefault(sid, {"name": r.get("source_name"), "sector": r.get("source_sector"), "subsector": r.get("source_subsector")})

    def ename(e):
        x = ents.get(e) or {}
        return (x.get("Name") or x.get("Full Name") or e or "").strip()

    def chains(e, depth=0, seen=()):
        """Every chain upward from owner e: [(top, share or None, [names])]."""
        ups = owners_of.get(e, [])
        if not ups or depth > 25:
            return [(e, 1.0, [ename(e)])]
        out = []
        for o, pct, _ in ups:
            if o in seen:
                continue
            for top, share, path in chains(o, depth + 1, seen + (e,)):
                s = None if (pct is None or share is None) else share * pct / 100
                out.append((top, s, [ename(e), f"{pct:g}%" if pct is not None else "share not given"] + path))
        return out or [(e, 1.0, [ename(e)])]

    tops = {}
    site_rows, all_chains = [], {}
    for sid, imm in site_owners.items():
        s = sites.get(sid)
        t_ = s["tonnes"] if s else None
        shares, lines, best_line = defaultdict(list), [], {}
        for e in dict.fromkeys(x for x in imm if x):
            for top, share, path in chains(e):
                line = " ← ".join(path)
                lines.append(line)
                shares[top].append(share)
                if top not in best_line or (share is not None and (best_line[top][0] is None or share > best_line[top][0])):
                    best_line[top] = (share, line)
        all_chains[sid] = list(dict.fromkeys(lines))
        # Counted once per owner at the top: the largest share any chain gives;
        # None (not divided) only where no chain to it gives every share.
        best = {top: (max(v for v in vs if v is not None) if any(v is not None for v in vs) else None) for top, vs in shares.items()}
        meta = site_meta[sid]
        for top, share in best.items():
            q = tops.setdefault(top, {"sites": 0, "weighted": 0.0, "unknown": 0.0, "whole": 0.0, "no_emissions": 0, "by_sector": defaultdict(float), "lines": []})
            q["sites"] += 1
            if t_ is None:
                q["no_emissions"] += 1
                q["lines"].append((0, f"{meta['name']} ({meta['subsector']}): emissions not read yet"))
                continue
            q["whole"] += t_
            if share is None:
                q["unknown"] += t_
                q["lines"].append((t_, f"{meta['name']} ({meta['subsector']}, {s.get('country') or ''}): {t_:,.0f} t CO2e ({s['year']}), share unknown, not divided"))
            else:
                q["weighted"] += t_ * share
                q["by_sector"][meta["sector"]] += t_ * share
                q["lines"].append((t_ * share, f"{meta['name']} ({meta['subsector']}, {s.get('country') or ''}): {share * 100:.4g}% of {t_:,.0f} t CO2e ({s['year']})"))
        if s and s.get("lat") is not None and s.get("lon") is not None:
            site_rows.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(s["lon"], 5), round(s["lat"], 5)]},
                              "properties": {"name": s.get("name") or meta["name"], "sector": meta["sector"], "subsector": meta["subsector"],
                                             "country": s.get("country"), "CO2e, tonnes (100-year)": s["tonnes"], "year": s["year"],
                                             "a full year": "yes" if s.get("full_year") else "no: the latest months Climate TRACE gives",
                                             "owners named for the site": "; ".join(ename(e) for e in dict.fromkeys(x for x in imm if x)),
                                             "owners at the top of its chains": "; ".join(ename(k) for k in best),
                                             "chain to each owner at the top (the one giving the largest share)": clip(" | ".join(l_ for _, l_ in best_line.values())),
                                             "chains in all": len(all_chains[sid]),
                                             "Climate TRACE source id": sid}})
    try:
        import pycountry  # noqa: F401
    except ImportError:
        import subprocess
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "pycountry"], check=False)
    from forest500_map import capitals
    caps = capitals()
    order = sorted(tops, key=lambda k: (-tops[k]["weighted"], -tops[k]["unknown"], -tops[k]["whole"]))
    feats, table, unplaced, spin = [], [], [], {}
    for rank, k in enumerate(order, 1):
        q, x = tops[k], ents.get(k) or {}
        q["lines"].sort(key=lambda tl: -tl[0])
        row = {"rank, by its shares": rank, "owner": ename(k), "Climate TRACE entity id": k, "kind": x.get("Entity Type") or "",
               "legal form": x.get("Legal Entity Type") or "", "publicly listed": x.get("PubliclyListed") or "",
               "headquarters country": x.get("Headquarters Country") or "", "registration country": x.get("Registration Country") or "",
               "home page": x.get("Home Page") or "", "GEM parents": x.get("Gem parents") or "",
               "sites": q["sites"],
               "CO2e by its shares, tonnes a year": round(q["weighted"]),
               "CO2e through chains of unknown share, not divided, tonnes a year": round(q["unknown"]),
               "CO2e of every site it sits above, not divided, tonnes a year": round(q["whole"]),
               "sites with emissions not read yet": q["no_emissions"],
               "by sector, by its shares": "; ".join(f"{s_}: {v:,.0f} t" for s_, v in sorted(q["by_sector"].items(), key=lambda kv: -kv[1])),
               "sites and shares": "; ".join(l_ for _, l_ in q["lines"])}
        table.append(row)
        if len(q["lines"]) > 15:
            # The map's box: its 15 largest holdings; every one is in top_owners.json.
            row = dict(row, **{"sites and shares": "; ".join(l_ for _, l_ in q["lines"][:15]) +
                               f"; and {len(q['lines']) - 15} more (every one in ct_ownership/top_owners.json)"})
        code = (x.get("Headquarters Country") or x.get("Registration Country") or "").strip().upper()
        cap = caps.get(code)
        if not cap:
            unplaced.append({"owner": row["owner"], "headquarters": x.get("Headquarters Country"), "registration": x.get("Registration Country")})
            continue
        i = spin[code] = spin.get(code, -1) + 1
        ang, rad = math.radians(137.508 * i), 0.12 * math.sqrt(i)
        lon = cap[0] + rad * math.cos(ang) / max(0.3, math.cos(math.radians(cap[1])))
        lat = max(-85, min(85, cap[1] + rad * math.sin(ang)))
        where = "headquarters" if x.get("Headquarters Country") else "registration"
        props = dict(row, **{"placed at": (f"the capital of its {where} country ({cap[2]})" if cap[3] == "capital" else f"{cap[2]}, in its {where} country") +
                             "; Climate TRACE gives the country, not the address. Spread so each can be clicked."})
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(lon, 5), round(lat, 5)]}, "properties": props})
    (DIR / "top_owners.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False))
    (DIR / "top_owners.json").write_text(json.dumps(table, ensure_ascii=False, indent=0))
    (DIR / "chains.json").write_text(json.dumps(all_chains, ensure_ascii=False))
    (DIR / "sites.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": site_rows}, ensure_ascii=False))
    status.update({"owners at the top": len(tops), "placed": len(feats), "not placed": unplaced[:500], "not placed, count": len(unplaced),
                   "sites named": len(site_owners), "sites with emissions": sum(1 for s in site_owners if s in sites), "sites drawn": len(site_rows)})
    (DIR / "build.json").write_text(json.dumps(status, indent=1, ensure_ascii=False))
    print(f"ct_ownership: {len(tops)} owners at the top, {len(feats)} placed; {status['sites with emissions']} of {len(site_owners)} sites with emissions; "
          f"waiting: {status['waiting']}", flush=True)


if __name__ == "__main__":
    main()
