#!/usr/bin/env python3
"""
Troutwood's map of listed companies worldwide as the map's own layers (round
105b, asked 28 September: its old "global assets" map, in place of the page in
a panel; and a Wreckers of the Earth layer for the whole world, not London
alone).

Read from troutwood/core.json, which scripts/troutwood.py copies daily from
the data Troutwood's own map reads: some 12,000 companies listed on the
world's stock exchanges, each with its head office's position, sector,
industry, market value, share price and Troutwood's note.

  troutwood/companies.geojson  every company with a position, every field
  troutwood/wreckers.geojson   those in the industries that wreck the planet,
                               each with its group (below) - the same kinds of
                               business Corporate Watch's Wreckers of the Earth
                               maps in London, by the industry Troutwood's data
                               gives each company; a classification by
                               industry, not a finding about any one company

Daily, after troutwood.py's copy.
"""
import json, pathlib

SRC = pathlib.Path("troutwood/core.json")
OUT = pathlib.Path("troutwood")
GROUPS = {
    "Fossil fuels": ["Oil & Gas Exploration & Production", "Oil & Gas Equipment & Services", "Oil & Gas Refining & Marketing",
                     "Oil & Gas Midstream", "Oil & Gas Integrated", "Oil & Gas Drilling", "Oil & Gas Energy", "Coal"],
    "Mining and metals": ["Gold", "Other Precious Metals", "Copper", "Aluminum", "Silver", "Steel", "Industrial Materials", "Uranium"],
    "Agribusiness, logging and paper": ["Agricultural Farm Products", "Agricultural Inputs", "Agricultural - Commodities/Milling",
                                        "Paper, Lumber & Forest Products"],
    "Chemicals and cement": ["Chemicals", "Chemicals - Specialty", "Construction Materials"],
    "Weapons": ["Aerospace & Defense"],
    "Aviation and shipping": ["Airlines, Airports & Air Services", "Marine Shipping"],
    "Tobacco": ["Tobacco"],
    "Big finance behind them": ["Banks - Diversified", "Investment - Banking & Investment Services", "Asset Management - Global"],
}
KIND = {ind: g for g, inds in GROUPS.items() for ind in inds}


def main():
    if not SRC.exists():
        raise SystemExit("troutwood_layers: troutwood/core.json not copied yet")
    d = json.loads(SRC.read_text(encoding="utf-8"))
    all_f, wreck = [], []
    for sym, c in (d.get("companies") or {}).items():
        lat, lon = c.get("latitude"), c.get("longitude")
        if lat is None or lon is None:
            continue
        p = {k: v for k, v in c.items() if k not in ("latitude", "longitude") and v not in (None, "")}
        p["group"] = c.get("sector") or "Not stated"
        f = {"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(lon, 5), round(lat, 5)]}, "properties": p}
        all_f.append(f)
        g = KIND.get(c.get("industry"))
        if g:
            wreck.append({"type": "Feature", "geometry": f["geometry"], "properties": dict(p, group=g)})
    OUT.mkdir(exist_ok=True)
    (OUT / "companies.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": all_f}, ensure_ascii=False, separators=(",", ":")))
    (OUT / "wreckers.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": wreck}, ensure_ascii=False, separators=(",", ":")))
    print(f"troutwood_layers: {len(all_f)} companies placed, {len(wreck)} in the wrecking industries")


if __name__ == "__main__":
    main()
