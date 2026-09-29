#!/usr/bin/env python3
"""
Where the threats are greatest, country by country: a combined index built
from the map's own country figures, rebuilt every day from their latest copies
(round 105b, asked 28 September: "given all this data, highlight the regions
most at threat per category, live").

Not an opinion and not written by an AI: every country's score is worked out
the same way, from figures the map already shows, and its box lists each
figure used, its value and its rank. Method:

  1. Each figure is turned into a rank among the countries that have it, from
     0 (the least threat of them) to 1 (the most). Figures where a higher
     number means less threat (democracy, resilience) are turned round.
  2. A category's score is the average of its figures' ranks, for a country
     with at least two of them; the combined score is the average of its
     category scores.

Categories and figures (each file as the map reads it, from this repository):
  Destruction of the planet
    - flora crimes, fauna crimes, non-renewable resource crimes (Global
      Organized Crime Index 2025, goc/countries.json)
    - fossil fuel subsidies, % of GDP (IMF, subsidies/imf_fossil_subsidies.json)
    - carbon dioxide per person (Global Carbon Project, via Our World in Data)
  Suppression of people
    - liberal democracy index, turned round (V-Dem, via Our World in Data)
    - human trafficking (Global Organized Crime Index 2025)
    - land and environmental defenders killed (Global Witness,
      global_witness/countries.json)
    - people in modern slavery per 1,000 (Walk Free, shapes/slavery_prevalence)
  Organised crime and captured states
    - criminality (Global Organized Crime Index 2025)
    - resilience to crime, turned round (Global Organized Crime Index 2025)

  threat/index.json   ISO3 -> {overall, destruction, suppression, crime, x_...}
  threat/build.json   the figures read, how many countries each covers

Daily.
"""
import csv, datetime, io, json, pathlib, re, urllib.request

OUT = pathlib.Path("threat")
UA = {"User-Agent": "Mozilla/5.0 (Culprits atlas build; welcometoyourgalaxy@gmail.com)"}
OWID = "https://ourworldindata.org/grapher/{}.csv?v=1&csvType=full&useColumnShortNames=true"


def load(path):
    p = pathlib.Path(path)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def owid(slug):
    raw = urllib.request.urlopen(urllib.request.Request(OWID.format(slug), headers=UA), timeout=120).read().decode("utf-8")
    rows = list(csv.DictReader(io.StringIO(raw)))
    col = [c for c in rows[0] if c not in ("Entity", "Code", "Year", "entity", "code", "year")][0]
    out = {}
    for r in rows:
        code, year = r.get("Code") or r.get("code"), r.get("Year") or r.get("year")
        try:
            v = float(r[col])
        except (TypeError, ValueError):
            continue
        if code and re.fullmatch(r"[A-Z]{3}", code) and (code not in out or int(year) > out[code][1]):
            out[code] = (v, int(year))
    return {k: v for k, (v, _) in out.items()}, {k: y for k, (_, y) in out.items()}


def main():
    figs, status = {}, {}

    def add(key, label, cat, values, higher_is_threat=True, years=None):
        values = {k: v for k, v in (values or {}).items() if isinstance(v, (int, float))}
        if values:
            figs[key] = {"label": label, "cat": cat, "values": values, "up": higher_is_threat, "years": years or {}}
        status[label] = len(values)

    goc = load("goc/countries.json") or {}
    gv = lambda name: {k: r.get(f"x_2025 {name}") for k, r in goc.items()}
    add("flora", "flora crimes (Global Organized Crime Index 2025, 1 to 10)", "destruction", gv("Flora crimes"))
    add("fauna", "fauna crimes (Global Organized Crime Index 2025, 1 to 10)", "destruction", gv("Fauna crimes"))
    add("nonren", "non-renewable resource crimes (Global Organized Crime Index 2025, 1 to 10)", "destruction", gv("Non-renewable resource crimes"))
    subs = load("subsidies/imf_fossil_subsidies.json") or {}
    add("subsidy", "fossil fuel subsidies, % of GDP (IMF)", "destruction", {k: r.get("value") for k, r in subs.items()})
    try:
        v, y = owid("co-emissions-per-capita")
        add("co2", "carbon dioxide per person, tonnes (Global Carbon Project, via Our World in Data)", "destruction", v, years=y)
    except Exception as e:  # noqa: BLE001
        status["carbon dioxide per person"] = f"not read ({e})"
    try:
        v, y = owid("liberal-democracy-index")
        add("vdem", "liberal democracy index, 0 to 1, turned round (V-Dem, via Our World in Data)", "suppression", v, higher_is_threat=False, years=y)
    except Exception as e:  # noqa: BLE001
        status["liberal democracy index"] = f"not read ({e})"
    add("traffick", "human trafficking (Global Organized Crime Index 2025, 1 to 10)", "suppression", gv("Human trafficking"))
    gw = load("global_witness/countries.json") or {}
    add("defenders", "land and environmental defenders killed or disappeared (Global Witness)", "suppression", {k: r.get("value") for k, r in gw.items()})
    prev = load("shapes/slavery_prevalence.geojson") or {}
    det = load("shapes/slavery_prevalence.details.json") or {}
    sl = {}
    for f in prev.get("features", []):
        p = f.get("properties") or {}
        iso = p.get("iso3") or p.get("ISO_A3") or p.get("ADM0_A3")
        d = det.get(str(p.get("_k"))) if det else None
        m = re.search(r"([\d.]+) people per 1,000", " ".join(str(x) for x in (d or {}).values())) if d else None
        if iso and m:
            sl[iso] = float(m.group(1))
    add("slavery", "people in modern slavery per 1,000 (Walk Free estimate)", "suppression", sl)
    add("crim", "criminality (Global Organized Crime Index 2025, 1 to 10)", "crime", gv("Criminality avg."))
    add("resil", "resilience to organised crime, turned round (Global Organized Crime Index 2025, 1 to 10)", "crime", gv("Resilience avg."), higher_is_threat=False)

    ranks = {}
    for key, f in figs.items():
        # Ties share one rank (the middle of the places they fill).
        vals = [v if f["up"] else -v for v in f["values"].values()]
        n = len(vals)
        for iso, v in f["values"].items():
            x = v if f["up"] else -v
            below, same = sum(1 for y in vals if y < x), sum(1 for y in vals if y == x)
            ranks.setdefault(iso, {})[key] = (below + (same - 1) / 2) / (n - 1) if n > 1 else 0.5
    out = {}
    names = {k: r.get("x_country") for k, r in goc.items()}
    for iso, rk in ranks.items():
        rec, cats = {}, {}
        for key, r in rk.items():
            f = figs[key]
            cats.setdefault(f["cat"], []).append(r)
            y = f["years"].get(iso)
            rec[f"x_{f['label']}{', ' + str(y) if y else ''}"] = round(f["values"][iso], 3)
            rec[f"x_{f['label']}: rank, 0 least to 1 most threat"] = round(r, 3)
        for cat, rs in cats.items():
            if len(rs) >= 2:
                rec[cat] = round(sum(rs) / len(rs), 3)
        have = [rec[c] for c in ("destruction", "suppression", "crime") if c in rec]
        if not have:
            continue
        rec["overall"] = round(sum(have) / len(have), 3)
        rec["x_categories counted"] = len(have)
        if names.get(iso):
            rec["x_country"] = names[iso]
        out[iso] = rec
    OUT.mkdir(exist_ok=True)
    (OUT / "index.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    (OUT / "build.json").write_text(json.dumps({"figures": status, "countries": len(out), "date": datetime.date.today().isoformat()}, indent=1, ensure_ascii=False))
    print(f"threat_index: {len(out)} countries; {status}")


if __name__ == "__main__":
    main()
