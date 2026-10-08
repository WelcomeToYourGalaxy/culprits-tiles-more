#!/usr/bin/env python3
"""
Methane from oil and gas, each country, 2025 (round 190o, asked 8 October).

The IEA's Global Methane Tracker 2026 (CC BY 4.0), its downloads, as the owner
saved them from the tracker's data pages into methane/iea/:

  by_source.csv     methane from oil and gas by country, hydrocarbon, sector,
                    production source and reason (vented, fugitive,
                    incomplete flare, abandoned facilities), thousand tonnes,
                    2025, with satellite-detected large emitters
  abatement.csv     each measure that would cut it, by country: thousand
                    tonnes saved and its cost in US dollars per MBtu of gas
  gas_prices.csv    the gas prices by region the tracker uses
  comparison.csv    the world's methane by sector (agriculture, energy,
                    waste, other) with the IEA's notes on its sources

Countries are drawn on the culprits map's own country shapes, shaded by any
of the measures (chosen in the box or the row); each country's box holds
every row of both tables for it. Rows for groups of countries (World,
European Union, "Rest of ...", "Other ...") and the two other tables are in
the row's "read them" window, whole.

  methane/iea_oilgas.places.geojson, methane/iea_oilgas.boxes.json,
  methane/iea_oilgas.build.json

Credit (the IEA's own terms): IEA (2026), Global Methane Tracker 2026, IEA,
Paris, Licence: CC BY 4.0, modified by Welcome to Your Galaxy (the sums and
the shading steps are ours; every figure is the IEA's).
"""
import csv, hashlib, html, json, pathlib, urllib.request
from collections import defaultdict

IN = pathlib.Path("methane/iea")
OUT = pathlib.Path("methane")
ROW = "iea_oilgas"
CULPRITS = "https://raw.githubusercontent.com/WelcomeToYourGalaxy/culprits/main/"
REPORT = "https://www.iea.org/reports/global-methane-tracker-2026"
CITE = ("IEA (2026), Global Methane Tracker 2026, IEA, Paris, https://www.iea.org/reports/global-methane-tracker-2026, "
        "Licence: CC BY 4.0, modified by Welcome to Your Galaxy")
UA = {"User-Agent": "WelcomeToYourGalaxy Culprits map (welcometoyourgalaxy@gmail.com)"}
# The IEA's spellings the map's name list does not have.
ALIAS = {"cote d'ivoire": "CIV", "côte ivoire": "CIV", "côte d'ivoire": "CIV", "democratic republic of congo": "COD", "korea": "KOR"}
STEPS = ["#D6EEF6", "#8FD6E8", "#3FA9C2", "#2275A8", "#13447A", "#0C2E5E"]
REASONS = ["Vented", "Fugitive", "Incomplete-flare", "Abandoned facilities"]
REASON_WORDS = {"Vented": "Vented on purpose", "Fugitive": "Leaked (fugitive)", "Incomplete-flare": "Not burned off in flares (incomplete flaring)",
                "Abandoned facilities": "From abandoned wells and mines"}


def get_json(path):
    local = pathlib.Path(path)
    if local.exists():
        return json.loads(local.read_text(encoding="utf-8"))
    with urllib.request.urlopen(urllib.request.Request(CULPRITS + path, headers=UA), timeout=120) as r:
        return json.loads(r.read())


def num(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def esc(s):
    return html.escape(str(s))


def kt(v):
    if v is None:
        return ""
    if v == 0:
        return "0"
    return f"{v:,.0f}" if abs(v) >= 100 else f"{v:,.1f}" if abs(v) >= 1 else f"{v:.3g}"


def table(head, rows, cls=""):
    th = "".join(f"<th>{esc(h)}</th>" for h in head)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<div class="io-scroll"><table class="{cls}"><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table></div>'


def emissions_html(rows):
    """One region's by_source rows -> a table: each production source, each reason."""
    grid = defaultdict(dict)
    order = []
    for r in rows:
        key = (r["Hydrocarbon"], r["Sector"], r["Production source"])
        if key not in grid:
            order.append(key)
        grid[key][r["Reason"]] = num(r["Value"])
    reasons = [x for x in REASONS if any(x in grid[k] for k in order)] + sorted({x for k in order for x in grid[k]} - set(REASONS))
    out = []
    for k in order:
        vals = [grid[k].get(x) for x in reasons]
        out.append([esc(k[0]), esc(k[1]), esc(k[2])] + [kt(v) for v in vals] + [f"<b>{kt(sum(v for v in vals if v))}</b>"])
    core = [k for k in order if k[0] in ("Oil", "Gas")]
    tot = [sum(grid[k].get(x) or 0 for k in core) for x in reasons]
    apart = len(core) < len(order)
    out.append(["<b>All oil and gas</b>" + (" (the satellite rows are not added in)" if apart else ""), "", ""] + [f"<b>{kt(v)}</b>" for v in tot] + [f"<b>{kt(sum(tot))}</b>"])
    return table(["Hydrocarbon", "Sector", "Production source"] + [REASON_WORDS.get(x, x) for x in reasons] + ["Total"], out)


def abatement_html(rows):
    rows = sorted(rows, key=lambda r: (num(r["cost (USD/MBtu)"]) if num(r["cost (USD/MBtu)"]) is not None else 1e9))
    out = [[esc(r["source"]), esc(r["segment"]), esc(r["type"]), esc(r["abatement"]), kt(num(r["savings (kt)"])),
            esc(r["cost (USD/MBtu)"])] for r in rows]
    return ('<div class="io-sub">Each measure as the IEA costs it. Some are alternatives to one another (leak checks yearly, quarterly or continuously), so their savings do not add up.</div>'
            + table(["Production source", "Segment", "Oil or gas", "Measure", "Methane saved (thousand tonnes)", "Cost (US$ per MBtu; below 0 pays for itself)"], out, "io-ab"))


def csv_html(path, delim):
    with open(path, encoding="utf-8-sig") as f:
        rows = list(csv.reader(f, delimiter=delim))
    return table(rows[0], [[esc(c) for c in r] for r in rows[1:] if r])


def nice(x):
    return f"{x:,.0f}" if x >= 100 else f"{x:.3g}"


def sextiles(vals):
    pos = sorted(v for v in vals if v and v > 0)
    if not pos:
        return [1e-9], ["0"]
    qs = []
    for i in range(1, 5):
        v = pos[min(len(pos) - 1, int(len(pos) * i / 5))]
        v = float(f"{v:.2g}")
        if not qs or v > qs[-1]:
            qs.append(v)
    breaks = [1e-9] + qs
    labels = ["0 (none estimated)"]
    lo = min(pos)
    for b in qs:
        labels.append(f"{nice(lo)} to {nice(b)}")
        lo = b
    labels.append(f"{nice(lo)} to {nice(max(pos))} (most)")
    return breaks, labels


CSS = """
:where(.wtyg-map-iea_oilgas) .io{font:12.5px/1.45 system-ui,sans-serif;color:#DCE6EA}
:where(.wtyg-map-iea_oilgas) .io h2{font-size:16px;margin:0 0 2px;color:#E8F1F4}
:where(.wtyg-map-iea_oilgas) .io-sub{color:#93A9B0;margin-bottom:6px}
:where(.wtyg-map-iea_oilgas) .io-big{font-size:13.5px;margin:4px 0 8px}
:where(.wtyg-map-iea_oilgas) .io-cap{font-weight:600;margin:8px 0 3px;color:#BFD8E0}
:where(.wtyg-map-iea_oilgas) .io-scroll{overflow:auto;max-width:100%;max-height:340px}
:where(.wtyg-map-iea_oilgas) table{border-collapse:collapse;font-size:11.5px}
:where(.wtyg-map-iea_oilgas) th,:where(.wtyg-map-iea_oilgas) td{border:1px solid #24404F;padding:2px 5px;vertical-align:top;text-align:left}
:where(.wtyg-map-iea_oilgas) th{position:sticky;top:0;background:#132430}
:where(.wtyg-map-iea_oilgas) td{white-space:nowrap}
:where(.wtyg-map-iea_oilgas) a{color:#8FC3D6}
:where(.wtyg-map-iea_oilgas) .io-pick{display:inline-block;margin:0 4px 4px 0;padding:1px 6px;border:1px solid #24404F;border-radius:3px;cursor:pointer;color:#BFD8E0}
:where(.wtyg-map-iea_oilgas) .io-foot{color:#93A9B0;margin-top:8px;font-size:11.5px}
.io-pop .maplibregl-popup-content{background:#0F1C26;color:#DCE6EA;max-height:540px;overflow:auto}
"""


def main():
    with open(IN / "by_source.csv", encoding="utf-8-sig") as f:
        src = list(csv.DictReader(f, delimiter=";"))
    with open(IN / "abatement.csv", encoding="utf-8-sig") as f:
        ab = list(csv.DictReader(f))
    names = get_json("pipeline/shapes/names_iso3.json")
    bounds = get_json("map/data/boundaries.geojson")
    shapes = {f["properties"]["iso3"]: f for f in bounds["features"]}
    by_name = {f["properties"]["name"].lower(): f["properties"]["iso3"] for f in bounds["features"]}

    def iso(n):
        n = n.strip().lower()
        i = ALIAS.get(n) or names.get(n) or by_name.get(n)
        return i if i in shapes else None

    src_by, ab_by = defaultdict(list), defaultdict(list)
    for r in src:
        src_by[r["Region"]].append(r)
    for r in ab:
        ab_by[r["country"]].append(r)
    year = sorted({r["Year"] for r in src})
    year = year[-1] if year else ""
    # The measures to shade by, each a sum of the IEA's own rows.
    # The IEA lists satellite-detected large emitters apart from oil and gas;
    # they are not added in, so nothing is counted twice.
    measures = [("all", "From oil and gas (satellite-detected large emitters shown apart)", lambda rs: [r for r in rs if r["Hydrocarbon"] in ("Oil", "Gas")])]
    measures += [(f"h_{h.lower()[:3]}", f"From {h.lower()}" if h in ("Oil", "Gas") else h, (lambda h: lambda rs: [r for r in rs if r["Hydrocarbon"] == h])(h))
                 for h in dict.fromkeys(r["Hydrocarbon"] for r in src)]
    measures += [(f"r_{i}", REASON_WORDS.get(x, x), (lambda x: lambda rs: [r for r in rs if r["Reason"] == x])(x))
                 for i, x in enumerate(dict.fromkeys(r["Reason"] for r in src))]
    measures += [(f"s_{i}", f"Source: {x}", (lambda x: lambda rs: [r for r in rs if r["Production source"] == x])(x))
                 for i, x in enumerate(dict.fromkeys(r["Production source"] for r in src))]
    regions = sorted(set(src_by) | set(ab_by))
    placed = {n: iso(n) for n in regions}
    feats, boxes, values = [], {}, defaultdict(dict)
    for n in regions:
        i = placed[n]
        if not i:
            continue
        rs = src_by.get(n, [])
        for k, _, pick in measures:
            if rs:
                values[n][k] = sum(num(r["Value"]) or 0 for r in pick(rs))
    # The measures that would cut it are not added up: several are
    # alternatives to one another (leak checks yearly, quarterly or
    # continuously), so a sum would count the same methane more than once.
    allm = measures
    colourings = []
    for k, label, _ in allm:
        br, lab = sextiles([values[n].get(k) for n in values if values[n].get(k) is not None])
        colourings.append({"k": k, "prop": f"v_{k}", "label": label, "note": "Thousand tonnes of methane a year" + (f", {year}" if year and not k.startswith("ab_") else "") + ", as the IEA estimates it.",
                           "breaks": br, "colours": STEPS[:len(br) + 1], "labels": lab})
    for n in regions:
        i = placed[n]
        if not i:
            continue
        v = values[n]
        k = hashlib.sha1(f"{ROW}|{i}".encode()).hexdigest()[:16]
        props = {"k": k, "n": n, "t": 1, "p": 1, "f": "|"}
        for m, _, _ in allm:
            if m in v:
                props[f"v_{m}"] = round(v[m], 4)
        feats.append({"type": "Feature", "geometry": shapes[i]["geometry"], "properties": props})
        rs, abr = src_by.get(n, []), ab_by.get(n, [])
        picks = "".join(f'<span class="io-pick" data-wtyg-colour="{esc(m)}">{esc(lbl)}</span>' for m, lbl, _ in allm[:3])
        big = []
        if "all" in v:
            big.append(f"<b>{kt(v['all'])} thousand tonnes</b> of methane from oil and gas in {esc(year)}")
        if v.get("h_sat"):
            big.append(f"and {kt(v['h_sat'])} thousand tonnes from large leaks seen by satellite")
        h = (f'<div class="io"><h2>{esc(n)}</h2><div class="io-sub">Methane from oil and gas (IEA Global Methane Tracker 2026)</div>'
             f'<div class="io-big">{" ".join(big)}.</div><div>Shade the map by: {picks}</div>'
             + (f'<div class="io-cap">Where it comes from and how it escapes, thousand tonnes, {esc(year)}</div>' + emissions_html(rs) if rs else "")
             + (f'<div class="io-cap">What would cut it: {len(abr)} measures, cheapest first</div>' + abatement_html(abr) if abr else "")
             + f'<div class="io-foot">Source: <a href="{REPORT}" target="_blank" rel="noopener">{esc(CITE)}</a>. Every figure is the IEA\'s; the totals and the shading steps are sums and groupings made for this map.</div></div>')
        boxes[k] = {"h": h, "o": {"maxWidth": 640, "minWidth": 320, "maxHeight": 540, "className": "io-pop"},
                    "t": f"{n}: {kt(v.get('all'))} thousand tonnes of methane from oil and gas" if "all" in v else n}
    groups = [n for n in regions if not placed[n]]
    entries = []
    for n in groups:
        part = ""
        if src_by.get(n):
            part += f'<div class="io-cap">Where it comes from and how it escapes, thousand tonnes, {esc(year)}</div>' + emissions_html(src_by[n])
        if ab_by.get(n):
            part += f'<div class="io-cap">What would cut it, cheapest first</div>' + abatement_html(ab_by[n])
        entries.append({"title": n, "kind": "a group of countries, not drawn", "html": f'<div class="io">{part}</div>'})
    for fn, title, d in (("comparison.csv", "The world's methane by sector, with the IEA's notes on its sources", ","),
                         ("gas_prices.csv", "Gas prices by region the tracker uses (US$ per MBtu)", ";")):
        if (IN / fn).exists():
            entries.append({"title": title, "kind": "the whole table", "html": f'<div class="io">{csv_html(IN / fn, d)}</div>'})
    name = f"Methane from oil and gas, each country, {year}, and what would cut it (IEA Global Methane Tracker 2026)"
    gj = {"type": "FeatureCollection", "name": name, "overlays": [], "filters": [], "colourings": colourings, "features": feats}
    out = {"name": name, "page": REPORT, "stylesheets": [], "chain": [], "css": CSS, "boxes": boxes,
           "entries": {"title": "Groups of countries and the tracker's other tables", "note": CITE + ". Rows the IEA gives for groups of countries cannot be drawn on one country, so they are here, whole.", "entries": entries}}
    OUT.mkdir(exist_ok=True)
    (OUT / f"{ROW}.places.geojson").write_text(json.dumps(gj, ensure_ascii=False, separators=(",", ":")))
    (OUT / f"{ROW}.boxes.json").write_text(json.dumps(out, ensure_ascii=False))
    (OUT / f"{ROW}.build.json").write_text(json.dumps({"source": CITE, "countries drawn": len(feats), "groups in the window": groups,
                                                         "measures": [c["label"] for c in colourings]}, ensure_ascii=False, indent=1))
    print(f"iea_methane: {len(feats)} countries drawn; {len(groups)} groups in the window")


if __name__ == "__main__":
    main()
