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
                               each with its group (below): Corporate Watch's
                               own sections of its Wreckers of the Earth
                               directory (2021), matched to the industry
                               Troutwood's data gives each company, with why
                               that section is on Corporate Watch's list; a
                               classification by industry, not a finding about
                               any one company

Daily, after troutwood.py's copy.
"""
import json, pathlib

SRC = pathlib.Path("troutwood/core.json")
OUT = pathlib.Path("troutwood")
# Round 119b (asked 30 September: "you added things like weapons, tobacco ...
# explain your methodology"): the groups are now Corporate Watch's own, from
# the sections of its Wreckers of the Earth directory (2021), each matched to
# the industries Troutwood's data uses. A company is on the layer only when
# its industry falls under one of them. Tobacco, airlines and general shipping
# are not in Corporate Watch's list and are no longer on the layer. Arms makers
# and security firms are: Corporate Watch lists them itself, among the
# "secondary planet-killers" that supply and guard the destruction.
# (group, Corporate Watch's section, Troutwood industries, why, in our words)
CW = [
    ("Oil, gas and coal", "1.1 and 1.2: hydrocarbon majors, smaller oil companies, frackers",
     ["Oil & Gas Exploration & Production", "Oil & Gas Integrated", "Oil & Gas Refining & Marketing", "Oil & Gas Midstream",
      "Oil & Gas Energy", "Coal"],
     "Corporate Watch puts the companies that dig up, pipe and refine oil, gas and coal first among its front-line planet-killers: burning what they sell drives climate breakdown."),
    ("Oil and gas services and drilling", "1.3: oil and gas services and shipping",
     ["Oil & Gas Equipment & Services", "Oil & Gas Drilling"],
     "Corporate Watch lists the drilling, equipment and service firms without which oil and gas could not be extracted."),
    ("Nuclear fuel", "1.4: non-fossil energy: nuclear, biomass, dams", ["Uranium"],
     "Corporate Watch lists nuclear power among the energy industries it counts as planet-killers; these companies mine or process its uranium."),
    ("Mining and metals", "1.5: mining",
     ["Gold", "Other Precious Metals", "Copper", "Aluminum", "Silver", "Steel", "Industrial Materials"],
     "Corporate Watch lists mining companies as front-line planet-killers, for the land, rivers and communities their mines destroy."),
    ("Engineering and construction", "1.6: engineering and construction", ["Engineering & Construction", "Construction"],
     "Corporate Watch lists the engineering and construction firms that build mines, pipelines, dams, roads and other destructive projects."),
    ("Agribusiness and logging", "1.7: agribusiness",
     ["Agricultural Farm Products", "Agricultural Inputs", "Agricultural - Commodities/Milling", "Paper, Lumber & Forest Products"],
     "Corporate Watch lists agribusiness (industrial farming, plantations, and the seeds and chemicals they run on) as a front-line planet-killer. Logging and paper companies are filed with it on this map, for the same clearing of forests; Corporate Watch's own list names agribusiness only."),
    ("Plastics, chemicals and cement", "1.8: plastics and chemical polluters (with cement, which it names among the front-line polluters)",
     ["Chemicals", "Chemicals - Specialty", "Construction Materials"],
     "Corporate Watch lists plastics and chemical producers, and cement makers, among the major polluters on the front line."),
    ("Banks", "2.1: banks", ["Banks - Diversified", "Banks"],
     "Corporate Watch lists the big banks among the secondary planet-killers: they lend to and raise money for the companies above."),
    ("Investment funds", "2.2: investment funds", ["Asset Management - Global", "Investment - Banking & Investment Services"],
     "Corporate Watch lists the investment funds and investment banks that own shares in, and raise money for, the companies above."),
    ("Insurers", "2.3: insurance companies", ["Insurance - Diversified", "Insurance - Reinsurance"],
     "Corporate Watch lists the insurers whose cover lets mines, pipelines and power plants be built and run."),
    ("Stock exchanges and rating agencies", "2.4: other finance (accountancy firms, rating agencies, stock exchanges)", ["Financial - Data & Stock Exchanges"],
     "Corporate Watch lists the stock exchanges and rating agencies through which the companies above raise money."),
    ("Arms makers and security firms", "2.6: military and security: arms makers and mercenary or security firms",
     ["Aerospace & Defense", "Security & Protection Services"],
     "Corporate Watch lists arms makers and security firms among the secondary planet-killers: not for harming the environment directly, but because they arm and guard the destruction (mines, pipelines, borders) and the wars over resources."),
]
GROUPS = {g: inds for g, _, inds, _ in CW}
WHY = {g: (sec, why) for g, sec, _, why in CW}
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
            sec, why = WHY[g]
            wreck.append({"type": "Feature", "geometry": f["geometry"], "properties": dict(p, group=g,
                **{"why it is on this layer": f"Troutwood's data gives its industry as {c.get('industry')}. {why}",
                   "Corporate Watch's section": f"Wreckers of the Earth directory (2021), section {sec}",
                   "how this layer was made": "By industry, not by anything this company has been found to do: every listed company "
                                              "in Troutwood's data whose industry falls under one of Corporate Watch's sections."})})
    OUT.mkdir(exist_ok=True)
    (OUT / "companies.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": all_f}, ensure_ascii=False, separators=(",", ":")))
    (OUT / "wreckers.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": wreck}, ensure_ascii=False, separators=(",", ":")))
    print(f"troutwood_layers: {len(all_f)} companies placed, {len(wreck)} in the wrecking industries")


if __name__ == "__main__":
    main()
