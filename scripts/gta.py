#!/usr/bin/env python3
"""
Global Trade Alert: every state act in its database, gathered daily and summed
by the country that took it, as its activity tracker map shows. Writes
  gta/countries.json   {country: {total, red, amber, green, in_force, types, latest: [...]}}
  gta/world.geojson    Global Trade Alert's own country shapes, so names join as on its map
The country is the one Global Trade Alert names at the start of each act's title
("Italy: ..."); a part of a country in brackets ("United Kingdom (Scotland)")
counts toward that country.
"""
import json, pathlib, re, sys, time, urllib.request

API = "https://api.globaltradealert.org/v1/state-act-snapshot/"
WORLD = "https://globaltradealert.org/maps/world.geojson"
OUT = pathlib.Path("gta")
LATEST = 60


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Culprits atlas daily copy)"})
    return json.loads(urllib.request.urlopen(req, timeout=180).read())


def main():
    OUT.mkdir(exist_ok=True)
    try:
        (OUT / "world.geojson").write_text(json.dumps(get(WORLD), separators=(",", ":")), encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        print(f"gta world shapes: {e}", file=sys.stderr)
    acts, limit, url = [], 1000, None
    while True:
        try:
            page = get(url or f"{API}?limit={limit}&offset={len(acts)}")
        except Exception as e:  # noqa: BLE001
            if limit > 100 and not acts:
                limit //= 2
                continue
            print(f"gta: stopped after {len(acts)} acts ({e})", file=sys.stderr)
            break
        acts.extend(page.get("results") or [])
        url = page.get("next")
        if not url:
            break
        time.sleep(0.5)
    if not acts:
        sys.exit("gta: nothing read; the last good copy stays")
    by = {}
    for a in acts:
        title = a.get("title") or ""
        who = re.sub(r"\s*\(.*?\)\s*$", "", title.split(":", 1)[0]).strip() if ":" in title else "Not named"
        c = by.setdefault(who, {"total": 0, "red": 0, "amber": 0, "green": 0, "in_force": 0, "types": {}, "latest": []})
        c["total"] += 1
        evals = [(i.get("gta_evaluation") or {}).get("name", "") for i in a.get("interventions") or []]
        worst = "Red" if "Red" in evals else "Amber" if "Amber" in evals else "Green" if "Green" in evals else ""
        if worst:
            c[worst.lower()] += 1
        if any(i.get("is_in_force") for i in a.get("interventions") or []):
            c["in_force"] += 1
        for i in a.get("interventions") or []:
            t = (i.get("intervention_type") or {}).get("name")
            if t:
                c["types"][t] = c["types"].get(t, 0) + 1
        c["latest"].append({"id": a.get("id"), "title": title, "date": a.get("date_announced"),
                            "eval": worst, "text": a.get("description") or "",
                            "types": sorted({(i.get("intervention_type") or {}).get("name", "") for i in a.get("interventions") or []} - {""})})
    for c in by.values():
        c["latest"] = sorted(c["latest"], key=lambda x: x["date"] or "", reverse=True)[:LATEST]
        c["types"] = dict(sorted(c["types"].items(), key=lambda kv: -kv[1])[:12])
    (OUT / "countries.json").write_text(json.dumps({"acts": len(acts), "countries": by}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"gta: {len(acts)} state acts across {len(by)} countries")


if __name__ == "__main__":
    main()
