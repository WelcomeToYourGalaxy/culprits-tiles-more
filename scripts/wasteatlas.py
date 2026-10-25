#!/usr/bin/env python3
"""
Waste Atlas (atlas.d-waste.com, D-Waste with ISWA, the University of Leeds and
others): every place its map draws, copied weekly into

  wasteatlas/places.geojson   one point per marker, every field kept
  wasteatlas/summary.json     what the file holds: its fields, and how many
                              markers carry each value of each short field

Its map reads one file, uploads/data.xml (found by pipeline/wasteatlas_probe.py
on 23 September). The site answers only over plain http (its https
certificate has expired), which a https page cannot read, so the map draws
this copy. Each marker's box is an HTML table of figures; its rows are kept as
fields, named as the table names them. Nothing is left out: a marker with no
position is counted in the summary, not dropped silently.

Weekly (Mondays) or by hand from the Actions tab.
"""
import html, json, os, pathlib, re, sys, time, urllib.request
import xml.etree.ElementTree as ET

SRC = "http://www.atlas.d-waste.com/uploads/data.xml"
OUT = pathlib.Path("wasteatlas")
LAT = ("lat", "latitude", "y")
LNG = ("lng", "lon", "long", "longitude", "x")


def cells(table_html):
    """The rows of a marker's box: (label, value) pairs, tags and entities removed."""
    text = html.unescape(table_html or "")
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", text, re.S | re.I):
        tds = [re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", td))).strip()
               for td in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S | re.I)]
        tds = [t for t in tds if t]
        if len(tds) >= 2:
            rows.append((tds[0], " | ".join(tds[1:])))
        elif len(tds) == 1:
            rows.append((tds[0], ""))
    return rows


def main():
    if time.gmtime().tm_wday != 0 and os.environ.get("GITHUB_EVENT_NAME", "workflow_dispatch") != "workflow_dispatch":
        print("wasteatlas: not Monday; copied weekly")
        return
    req = urllib.request.Request(SRC, headers={"User-Agent": "Mozilla/5.0 (Culprits atlas weekly copy)"})
    raw = urllib.request.urlopen(req, timeout=180).read()
    # Round 97b (28 September): on 28 September the file would not parse as
    # XML ("mismatched tag", line 93). Each marker is then read on its own, so
    # one broken marker, or a page wrapped round the file, does not stop the
    # rest; what could not be read is counted and shown.
    try:
        markers = [dict(m.attrib) for m in ET.fromstring(raw).iter("marker")]
    except ET.ParseError as e:
        text = raw.decode("utf-8", "replace")
        found = re.findall(r"""<marker\b((?:\s+[\w:-]+\s*=\s*(?:"[^"]*"|'[^']*'))*)\s*/?>""", text, re.I)
        markers = []
        for body in found:
            a = {k: html.unescape(v1 if v1 is not None and q == '"' else v2)
                 for k, q, v1, v2 in ((m.group(1), m.group(2), m.group(3), m.group(4))
                                      for m in re.finditer(r'([\w:-]+)\s*=\s*(?:(")([^"]*)"|\'([^\']*)\')', body))}
            if a:
                markers.append(a)
        print(f"wasteatlas: the file is not well-formed XML ({e}); {len(markers):,} markers read one by one "
              f"from {len(found):,} marker tags", flush=True)
        if not markers:
            print(f"wasteatlas: what came back ({len(raw):,} bytes) begins: {text[:400]!r}", flush=True)
    feats, nowhere, attrs, values = [], 0, {}, {}
    for a in markers:
        for k in a:
            attrs[k] = attrs.get(k, 0) + 1
        lat = next((a[k] for k in a if k.lower() in LAT), None)
        lng = next((a[k] for k in a if k.lower() in LNG), None)
        props = {k: v for k, v in a.items() if k != "address"}
        for label, value in cells(a.get("address")):
            key = label if label not in props else f"{label} (box)"
            props[key] = value
        for k, v in props.items():
            if isinstance(v, str) and len(v) <= 40:
                values.setdefault(k, {})
                values[k][v] = values[k].get(v, 0) + 1
        try:
            x, y = float(lng), float(lat)
            if not (-180 <= x <= 180 and -90 <= y <= 90):
                raise ValueError
        except (TypeError, ValueError):
            nowhere += 1
            continue
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [x, y]}, "properties": props})
    if not feats:
        sys.exit(f"wasteatlas: no marker with a position in {len(raw):,} bytes; the last copy stays")
    OUT.mkdir(exist_ok=True)
    (OUT / "places.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats},
                                                   ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    # Short fields with few values are the likely kinds (dumpsite, landfill ...);
    # all are listed so the rows can be made from what the file really says.
    few = {k: dict(sorted(v.items(), key=lambda kv: -kv[1])) for k, v in values.items() if len(v) <= 40}
    (OUT / "summary.json").write_text(json.dumps({"source": SRC, "markers": len(feats) + nowhere, "placed": len(feats),
                                                  "no_position": nowhere, "attributes": attrs, "values": few},
                                                 ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wasteatlas: {len(feats):,} markers placed, {nowhere:,} with no position; attributes: {', '.join(attrs)}")


if __name__ == "__main__":
    main()
