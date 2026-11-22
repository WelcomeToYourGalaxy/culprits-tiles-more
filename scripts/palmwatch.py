#!/usr/bin/env python3
"""
Reread PalmWatch (Inclusive Development International and the University of
Chicago Data Science Institute) from its own public routes and write it as a
map Culprits can draw, the way PalmWatch draws it:

  sitemaps/palmwatch.places.geojson   every mill's sourcing area (the
                                      "catchment"), with the values PalmWatch
                                      colours it by and the filters under its row
  sitemaps/palmwatch.boxes.json       what a click opens: the mill's details as
                                      PalmWatch lists them, the brands that
                                      disclosed buying from it, and its tree
                                      cover loss year by year

Nothing is dropped: every mill PalmWatch publishes is carried, and a mill whose
brand list could not be read says so in its box rather than showing none.

Run by .github/workflows/refresh.yml every day. By hand, from the repo root:
  python3 scripts/palmwatch.py
Set PALMWATCH to point at another address (the tests use a local copy).
"""
import html
import json
import os
import pathlib
import re
import sys
import time
import urllib.parse
import urllib.request

BASE = os.environ.get("PALMWATCH", "https://palmwatch.inclusivedevelopment.net").rstrip("/")
OUT = pathlib.Path(os.environ.get("PALMWATCH_OUT", "sitemaps"))
ID = "palmwatch"

# PalmWatch's own breaks. Its colours are yellow-to-red and purple-to-orange;
# these keep the order and the steps but in the atlas's muted, earthy range.
LOSS_BREAKS = [0.25, 1.5, 4.5, 10]
LOSS_LABELS = ["0 - 0.25 km\u00b2", "0.25 - 1.5 km\u00b2", "1.5 - 4.5 km\u00b2", "4.5 - 10 km\u00b2", "> 10 km\u00b2"]
LOSS_COLOURS = ["#D8D0C2", "#C3A897", "#A67D6D", "#87544A", "#63302C"]
SCORE_COLOURS = ["#5D5370", "#9D97AE", "#D6D2CA", "#B08A78", "#8A5A46"]

FIELDS = [  # PalmWatch's mill details, in its order and with its labels
    ("Mill Name", "Mill Name"),
    ("Current Deforestation Score", "Recent Deforestation Score"),
    ("Past Deforestation Score", "Past Deforestation Score"),
    ("Future Risk Score", "Future Deforestation Risk Score"),
    ("Alternative name", "Alternative name"),
    ("Group Name", "Group Name"),
    ("Parent Company", "Parent Company"),
    ("RSPO Status", "RSPO Status"),
    ("RSPO Type", "RSPO Type"),
    ("Confidence level", "Confidence level"),
    ("Date RSPO Certification Status", "Date RSPO Certification Status"),
    ("Country", "Country"),
    ("Province", "Province"),
    ("District", "District"),
    ("UML ID", "UML ID"),
]


def get(path, tries=4):
    url = BASE + path
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Culprits atlas refresh)"})
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            if i == tries - 1:
                raise RuntimeError(f"{url}: {e}") from e
            time.sleep(5 * (i + 1))


def rounded(coords):
    if isinstance(coords, (int, float)):
        return round(coords, 5)
    return [rounded(c) for c in coords]


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def brand_rows(payload):
    """The brand route's mill list, wherever the reply keeps it."""
    rows = payload.get("umlInfo") if isinstance(payload, dict) else None
    if isinstance(rows, dict):
        rows = list(rows.values())
    return [r for r in (rows or []) if isinstance(r, dict) and r.get("UML ID")]


def main():
    geo = get("/api/download?output=geo")
    feats = geo.get("features") or []
    if not feats:
        sys.exit("PalmWatch returned no mills; nothing written (the last good copy stays).")

    years = sorted({int(m.group(1)) for f in feats for k in (f.get("properties") or {})
                    if (m := re.fullmatch(r"treeloss_km_(\d{4})", k))})
    latest = years[-1] if years else None

    # Which brands disclosed buying from which mill.
    buyers, brand_problem = {}, None
    try:
        listing = get("/api/list")
        for b in listing.get("Brands") or []:
            name = b.get("label")
            if not name:
                continue
            data = get("/api/brand/" + urllib.parse.quote(name))
            for row in brand_rows(data):
                yrs = row.get("years")
                yrs = sorted(yrs) if isinstance(yrs, list) else []
                buyers.setdefault(row["UML ID"], []).append((name, yrs))
            time.sleep(1)
    except Exception as e:  # noqa: BLE001
        brand_problem = str(e)
        print(f"  brands could not all be read: {e}", file=sys.stderr)

    places, boxes = [], {}
    counts = {"country": {}, "rspo": {}, "cur": {}}
    for f in feats:
        p = f.get("properties") or {}
        uml = str(p.get("UML ID") or "")
        if not uml or not f.get("geometry"):
            continue
        cur, past, fut = (p.get("Current Deforestation Score"), p.get("Past Deforestation Score"),
                          p.get("Future Risk Score"))
        country, rspo = p.get("Country") or "Not stated", p.get("RSPO Status") or "Not stated"
        keys = [f"country:{country}", f"rspo:{rspo}", f"cur:{cur}"]
        for fam, v in (("country", country), ("rspo", rspo), ("cur", cur)):
            counts[fam][v] = counts[fam].get(v, 0) + 1
        props = {"k": uml, "p": 1, "n": str(p.get("Mill Name") or uml), "t": 1, "c": LOSS_COLOURS[2], "f": "|" + "|".join(keys) + "|",
                 "cur": cur, "past": past, "fut": fut}
        for y in years:
            v = num(p.get(f"treeloss_km_{y}"))
            if v is not None:
                props[f"l{y}"] = round(v, 4)
        places.append({"type": "Feature", "properties": props,
                       "geometry": {"type": f["geometry"]["type"], "coordinates": rounded(f["geometry"]["coordinates"])}})

        rows = "".join(
            f"<tr><th>{html.escape(label)}</th><td>{html.escape(str(p.get(col)))}</td></tr>"
            for col, label in FIELDS if p.get(col) not in (None, ""))
        mine = buyers.get(uml, [])
        if mine:
            brands = "<ul class=\"pw-brands\">" + "".join(
                f"<li>{html.escape(n)}{(' <span>(' + ', '.join(str(y) for y in ys) + ')</span>') if ys else ''}</li>"
                for n, ys in sorted(mine)) + "</ul>"
        elif brand_problem:
            brands = "<p class=\"pw-note\">The brand list could not be read on the last refresh.</p>"
        else:
            brands = "<p class=\"pw-note\">No brand in PalmWatch's set has disclosed buying from this mill.</p>"
        loss = [(y, num(p.get(f"treeloss_km_{y}")) or 0.0) for y in years]
        top = max([v for _, v in loss] + [0.0001])
        bars = "".join(
            f"<div class=\"pw-bar\" title=\"{y}: {v:.2f} km\u00b2\" style=\"height:{max(1, round(40 * v / top))}px\"></div>"
            for y, v in loss)
        chart = (f"<div class=\"pw-chart\">{bars}</div><div class=\"pw-axis\"><span>{years[0]}</span><span>{years[-1]}</span></div>"
                 if years else "")
        total = num(p.get("sum_of_treeloss_km"))
        area = num(p.get("km_area"))
        facts = []
        if area is not None:
            facts.append(f"Catchment area: {area:,.1f} km\u00b2")
        if total is not None:
            facts.append(f"Tree cover loss {years[0]}\u2013{years[-1]}: {total:,.1f} km\u00b2" if years else f"Tree cover loss: {total:,.1f} km\u00b2")
        link = f"{BASE}/mill/{urllib.parse.quote(uml)}"
        boxes[uml] = {
            "h": (f"<div class=\"pw-box\"><h3>{html.escape(str(p.get('Mill Name') or uml))}</h3>"
                  f"<table>{rows}</table><h4>Brands sourcing from this mill</h4>{brands}"
                  f"<h4>Tree cover loss in the catchment, km\u00b2 per year</h4>{chart}"
                  + "".join(f"<p class=\"pw-fact\">{html.escape(x)}</p>" for x in facts) +
                  "<p class=\"pw-note\">The catchment is PalmWatch's modelled sourcing area around the mill, not a property "
                  "boundary; tree cover loss inside it is not measured as the mill's own clearing.</p>"
                  f"<p><a href=\"{link}\" target=\"_blank\" rel=\"noopener\">Open this mill on PalmWatch</a></p></div>"),
            "o": {"maxWidth": 360, "maxHeight": 420, "className": "pw-popup"},
            "t": (f"<b>{html.escape(str(p.get('Mill Name') or uml))}</b><br>{html.escape(str(p.get('Group Name') or ''))}"
                  + (f"<br>Tree cover loss {latest}: {num(p.get(f'treeloss_km_{latest}')) or 0:.2f} km\u00b2" if latest else "")),
        }

    def facet(label, fam, order=None):
        vals = sorted(counts[fam], key=order or (lambda v: str(v)))
        return {"label": label, "values": [{"k": f"{fam}:{v}", "label": str(v), "n": counts[fam][v]} for v in vals]}

    colourings = []
    if latest:
        colourings.append({"k": "loss", "label": "Tree cover loss", "years": years, "prop": "l{year}", "year": latest,
                           "breaks": LOSS_BREAKS, "colours": LOSS_COLOURS, "labels": LOSS_LABELS})
    for k, label in (("cur", "Recent Deforestation Score"), ("past", "Past Deforestation Score"),
                     ("fut", "Future Deforestation Risk Score")):
        colourings.append({"k": k, "label": label, "prop": k, "scores": [1, 2, 3, 4, 5],
                           "colours": SCORE_COLOURS, "labels": ["1", "2", "3", "4", "5"]})

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{ID}.places.geojson").write_text(json.dumps({
        "type": "FeatureCollection", "name": "PalmWatch", "overlays": [],
        "filters": [facet("Recent Deforestation Score", "cur"), facet("RSPO Status", "rspo"), facet("Country", "country")],
        "colourings": colourings, "features": places}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    css = (".wtyg-map-palmwatch .pw-box{font:13px/1.4 system-ui,sans-serif;color:#1d1b17}"
           ".wtyg-map-palmwatch .pw-box h3{margin:0 0 6px;font-size:15px}"
           ".wtyg-map-palmwatch .pw-box h4{margin:10px 0 4px;font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:#5a544a}"
           ".wtyg-map-palmwatch .pw-box table{border-collapse:collapse;width:100%}"
           ".wtyg-map-palmwatch .pw-box th{text-align:left;font-weight:600;padding:2px 8px 2px 0;vertical-align:top;color:#4a453d;white-space:nowrap}"
           ".wtyg-map-palmwatch .pw-box td{padding:2px 0}"
           ".wtyg-map-palmwatch .pw-brands{margin:0;padding-left:18px}.wtyg-map-palmwatch .pw-brands span{color:#6b645a}"
           ".wtyg-map-palmwatch .pw-chart{display:flex;align-items:flex-end;gap:1px;height:42px;border-bottom:1px solid #9a9184}"
           ".wtyg-map-palmwatch .pw-bar{flex:1;background:#87544A}"
           ".wtyg-map-palmwatch .pw-axis{display:flex;justify-content:space-between;font-size:11px;color:#6b645a}"
           ".wtyg-map-palmwatch .pw-note{font-size:11px;color:#6b645a}.wtyg-map-palmwatch .pw-fact{margin:4px 0}")
    (OUT / f"{ID}.boxes.json").write_text(json.dumps({
        "name": "PalmWatch", "css": css, "stylesheets": [], "chain": [{"tag": "div", "class": "palmwatch-map"}],
        "boxes": boxes}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"palmwatch: {len(places)} mills, {len(buyers)} with a disclosing brand, years {years[0] if years else '-'}-{latest or '-'}")


if __name__ == "__main__":
    main()
