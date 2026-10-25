"""The Genetic engineering map's own records written into its page (PJ_SEED).

Written 30 September (round 118b). The owner found the row of genetic
engineering companies, labs, funders, regulators and trade bodies empty: the
map read those organisations (and the escapes and contamination records) from
the releases archive, but they are not in the GMO map's projects.json, which
that archive is built from; they live only in its page, in the PJ_SEED list.
Here that list is read from the page each day, every field kept, and written
as two files the map reads:

  gmo/organisations.geojson   the organisations (sources industry:*), by the
                              map's own lenses, except the animal research and
                              fertility rows, which have rows of their own
  gmo/escapes.geojson         escapes and contamination (sources escape:*)
  gmo/seed_build.json         counts, and records with no position
  gmo/trials/<XX>.json        every US release authorisation (APHIS) the map
                              holds, state by state (two-letter code), for the
                              boxes of the field trials row, which gave only a
                              count (the GMO map's own state markers list them)
"""
import json, pathlib, time, urllib.request

PAGE = "https://raw.githubusercontent.com/WelcomeToYourGalaxy/GMO-map/main/index.html"
PROJECTS = "https://raw.githubusercontent.com/WelcomeToYourGalaxy/GMO-map/main/projects.json"
STATES = {"AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado", "CT": "Connecticut",
          "DE": "Delaware", "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois",
          "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
          "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri", "MT": "Montana",
          "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
          "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania",
          "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
          "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
          "PR": "Puerto Rico", "GU": "Guam", "VI": "US Virgin Islands", "AS": "American Samoa", "MP": "Northern Mariana Islands"}
OUT = pathlib.Path("gmo")
LENSES = {"industry:seed": "Seed and traits", "industry:editing": "Gene editing and synthetic biology",
          "industry:synthesis": "DNA synthesis and sequencing", "industry:cro": "Contract research and manufacturing",
          "industry:livestock": "Livestock, aquaculture and pets", "industry:wild": "Insects, microbes and open release",
          "industry:deextinct": "De-extinction and conservation biotech", "industry:clinical": "Human clinical and therapeutic",
          "industry:money": "Money and backers", "industry:rules": "Rules, records and advocacy",
          "escape:crop": "Crops", "escape:animal": "Animals"}


def main():
    req = urllib.request.Request(PAGE, headers={"User-Agent": "Culprits atlas build (github.com/WelcomeToYourGalaxy)"})
    page = urllib.request.urlopen(req, timeout=120).read().decode("utf-8")
    at = page.index("var PJ_SEED=") + len("var PJ_SEED=")
    seed, _ = json.JSONDecoder().raw_decode(page[at:])
    rows = seed.get("projects") or []
    files = {"organisations": [], "escapes": []}
    nowhere = {"organisations": 0, "escapes": 0}
    for r in rows:
        src = str(r.get("source") or "")
        which = ("organisations" if src.startswith("industry:") and src not in ("industry:animals", "industry:repro")
                 else "escapes" if src.startswith("escape:") else None)
        if not which:
            continue
        if r.get("lat") is None or r.get("lng") is None:
            nowhere[which] += 1
            continue
        props = {k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v) for k, v in r.items() if k not in ("lat", "lng")}
        props["group"] = LENSES.get(src, src)
        files[which].append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [float(r["lng"]), float(r["lat"])]}, "properties": props})
    OUT.mkdir(exist_ok=True)
    for name, feats in files.items():
        (OUT / f"{name}.geojson").write_text(json.dumps({"type": "FeatureCollection", "source": PAGE, "features": feats}, ensure_ascii=False))
    (OUT / "seed_build.json").write_text(json.dumps({"built": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "records_in_page": len(rows),
                                                     "placed": {k: len(v) for k, v in files.items()}, "no_position": nowhere}, indent=1))
    print("gmo_seed:", {k: len(v) for k, v in files.items()}, "no position:", nowhere)
    trials()


def trials():
    import re
    req = urllib.request.Request(PROJECTS, headers={"User-Agent": "Culprits atlas build (github.com/WelcomeToYourGalaxy)"})
    rows = json.loads(urllib.request.urlopen(req, timeout=300).read()).get("projects") or []
    by = {}
    for r in rows:
        if not isinstance(r, dict) or not str(r.get("source") or "").startswith("aphis"):
            continue
        keep = {k: r.get(k) for k in ("name", "date", "type", "company", "status", "size", "url", "source") if r.get(k) not in (None, "")}
        for st in re.findall(r"\b[A-Z]{2}\b", str(r.get("state") or "")):
            by.setdefault(st, []).append(keep)
    d = OUT / "trials"
    d.mkdir(parents=True, exist_ok=True)
    for st, recs in by.items():
        recs.sort(key=lambda x: str(x.get("date") or ""), reverse=True)
        (d / f"{st}.json").write_text(json.dumps({"state": STATES.get(st, st), "records": recs}, ensure_ascii=False, separators=(",", ":")))
    (d / "index.json").write_text(json.dumps({STATES.get(st, st): {"code": st, "records": len(v)} for st, v in sorted(by.items())}, indent=0))
    print(f"gmo_seed: release authorisations listed for {len(by)} states and territories")


if __name__ == "__main__":
    main()
