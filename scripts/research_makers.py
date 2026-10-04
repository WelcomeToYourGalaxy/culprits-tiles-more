#!/usr/bin/env python3
"""
Who manufactures fake science: the second tab of the site's own World Research
Integrity 2026 map (round 103b, asked 28 September: its paper mills, predatory
operators, named record-setting fabricators and enablers had not reached the
Culprits map; only its first tab, publishers and journals, had).

Read from the page itself each week (the maps repo), both tabs, every field of
every entry as the page writes it, with the page's own rank (its order: tier,
then documented scale).

  research/makers.geojson      the "Who makes it" tab
  research/publishers.geojson  the "Publishers & journals" tab
  research/build.json
"""
import datetime, json, os, pathlib, re, subprocess, tempfile, urllib.request

PAGE = "https://raw.githubusercontent.com/WelcomeToYourGalaxy/maps/main/site/site_research_integrity.html"
OUT = pathlib.Path("research")
UA = {"User-Agent": "Mozilla/5.0 (Culprits atlas build; welcometoyourgalaxy@gmail.com)"}
# The page's own category names, said plainly for the map's rows.
PLAIN = {
    "paper_mill": "Fake-paper factories that sell authorship (paper mills)",
    "operator": "Predatory operators",
    "fraudster": "Named scientists with the most fabricated or retracted papers",
    "enabler": "Enablers: citation rings, hijacked journals, AI-written papers, essay mills",
    "infiltrated": "Big publishers that printed papers bought from paper mills, then retracted them",
    "megajournal": "Journals publishing huge numbers of papers fast, criticised for weak checks (megajournals)",
    "predatory": "Publishers that take fees but skip real checking (predatory), fined or blacklisted",
    "conference": "Fake or pay-to-present science conferences",
}


def main():
    raw = urllib.request.urlopen(urllib.request.Request(PAGE, headers=UA), timeout=120).read().decode("utf-8")
    parts = {}
    for name in ("CATS_PUB", "CATS_MAKE", "DATA_PUB", "DATA_MAKE"):
        m = re.search(rf"const {name}\s*=\s*([\[{{][\s\S]*?\n[\]}}]);", raw)
        if not m:
            raise SystemExit(f"research_makers: {name} not found on the page")
        parts[name] = m.group(1)
    js = "const o = {" + ",".join(f"{k}: {v}" for k, v in parts.items()) + "}; process.stdout.write(JSON.stringify(o));"
    f = pathlib.Path(tempfile.mkdtemp()) / "read.js"
    f.write_text(js, encoding="utf-8")
    d = json.loads(subprocess.run(["node", str(f)], capture_output=True, text=True, check=True).stdout)
    OUT.mkdir(exist_ok=True)
    counts = {}
    for tab, data, cats, out in (("Who makes it", d["DATA_MAKE"], d["CATS_MAKE"], "makers"), ("Publishers & journals", d["DATA_PUB"], d["CATS_PUB"], "publishers")):
        rows = sorted(data, key=lambda r: (r.get("tier", 9), -(r.get("mag") or 0)))
        feats = []
        for i, r in enumerate(rows, 1):
            if r.get("lat") is None or r.get("lng") is None:
                continue
            cat = r.get("cat", "")
            props = {"name": r.get("n", ""), "group": PLAIN.get(cat, (cats.get(cat) or {}).get("label", cat)),
                     "type, as the page says": (cats.get(cat) or {}).get("label", cat), "rank on the page": i,
                     "based": r.get("hq", ""), "documented scale": r.get("scale", ""), "detail": r.get("detail", ""),
                     "tier": r.get("tier"), "size of the record": r.get("mag")}
            if r.get("note"):
                props["note"] = r["note"]
            for k, v in r.items():
                if k not in ("n", "hq", "lat", "lng", "cat", "tier", "mag", "scale", "detail", "note"):
                    props[k] = v
            feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [r["lng"], r["lat"]]}, "properties": props})
        (OUT / f"{out}.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False))
        counts[tab] = len(feats)
    (OUT / "build.json").write_text(json.dumps({"page": PAGE, "entries": counts, "date": datetime.date.today().isoformat()}, indent=1))
    print(f"research_makers: {counts}")


if __name__ == "__main__":
    main()
