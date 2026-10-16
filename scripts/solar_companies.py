#!/usr/bin/env python3
"""
The solar industry's companies (round 209o, asked 15 October 2026: "the
companies most active/influential in the solar industry ... solar panels and
stuff"): Wikipedia's "List of photovoltaics companies", every table on the page
that names companies (shipments by year, production lines, polysilicon,
cell and module makers, factories), every row and every column as written,
with the section each table sits under. Wikipedia text is CC BY-SA 4.0.

Each row is placed at its company's headquarters as Wikidata records it
(the company's "headquarters location" and that place's coordinates; or, if
Wikidata gives none, the company's own coordinates). Wikidata is CC0. A row
whose company has no Wikipedia link, or whose headquarters Wikidata does not
place, is kept with no position, and the map lists it as unplaced.

Writes solar/companies.geojson (and solar/companies_build.json).
"""
import json, pathlib, re, time, urllib.parse, urllib.request
from html.parser import HTMLParser

PAGE = "List_of_photovoltaics_companies"
WP = "https://en.wikipedia.org/w/api.php"
WD = "https://www.wikidata.org/w/api.php"
OUT = pathlib.Path("solar")
UA = {"User-Agent": "Culprits atlas build (welcometoyourgalaxy@gmail.com)"}
VOID = {"br", "img", "hr", "meta", "link", "input", "wbr", "col", "source"}


def get(url, tries=4):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as r:
                return r.read().decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            if i == tries - 1:
                raise
            time.sleep(4 * (i + 1))


class Page(HTMLParser):
    """Wikitables with each cell's text and the first article it links to,
    and the section heading each table sits under."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables, self.stack, self.cell, self.skip = [], [], None, 0
        self.heading, self.in_h = "", None

    def handle_starttag(self, tag, a):
        a = dict(a)
        if tag in ("h2", "h3", "h4") and not self.stack:
            self.in_h = []
        if tag in ("sup", "style", "script"):
            self.skip += 1
        if tag == "table":
            self.stack.append({"wiki": "wikitable" in (a.get("class") or ""), "rows": [], "section": self.heading})
        elif self.stack and tag == "tr":
            self.stack[-1]["rows"].append([])
        elif self.stack and tag in ("td", "th"):
            n = lambda v: int(re.sub(r"\D", "", v or "1") or 1)  # noqa: E731
            if not self.stack[-1]["rows"]:
                self.stack[-1]["rows"].append([])
            self.cell = {"th": tag == "th", "text": [], "link": None, "rs": n(a.get("rowspan")), "cs": n(a.get("colspan"))}
        elif self.cell is not None and tag == "a" and not self.cell["link"] and not self.skip:
            href = a.get("href") or ""
            if href.startswith("/wiki/") and ":" not in href[6:]:
                self.cell["link"] = urllib.parse.unquote(href[6:].split("#")[0])
        elif self.cell is not None and tag == "br":
            self.cell["text"].append(" ")

    def handle_endtag(self, tag):
        if tag in ("sup", "style", "script") and self.skip:
            self.skip -= 1
        if tag in ("h2", "h3", "h4") and self.in_h is not None:
            self.heading = " ".join("".join(self.in_h).replace("[edit]", "").split())
            self.in_h = None
        if not self.stack:
            return
        if tag in ("td", "th") and self.cell is not None:
            c = self.cell
            c["text"] = " ".join("".join(c["text"]).split())
            self.stack[-1]["rows"][-1].append(c)
            self.cell = None
        elif tag == "table":
            t = self.stack.pop()
            if t["wiki"]:
                self.tables.append(t)

    def handle_data(self, d):
        if self.in_h is not None:
            self.in_h.append(d)
        if self.cell is not None and not self.skip:
            self.cell["text"].append(d)


def grid(rows):
    out, carry = [], {}
    for row in rows:
        line, col, cells = [], 0, list(row)
        while cells or col in carry:
            if col in carry:
                cell, left = carry[col]
                line.append(cell)
                if left > 1:
                    carry[col] = (cell, left - 1)
                else:
                    del carry[col]
                col += 1
                continue
            c = cells.pop(0)
            for _ in range(c["cs"]):
                line.append(c)
                if c["rs"] > 1:
                    carry[col] = (c, c["rs"] - 1)
                col += 1
        out.append(line)
    return out


def wikidata_places(titles):
    """Article title -> (lon, lat, what was used), from Wikidata."""
    qid = {}
    for i in range(0, len(titles), 40):
        part = titles[i:i + 40]
        q = urllib.parse.urlencode({"action": "query", "prop": "pageprops", "ppprop": "wikibase_item", "redirects": 1,
                                    "titles": "|".join(part), "format": "json"})
        d = json.loads(get(f"{WP}?{q}"))
        back = {}
        for r in d.get("query", {}).get("redirects", []) + d.get("query", {}).get("normalized", []):
            back[r["to"]] = back.get(r["from"], r["from"])
        for p in d.get("query", {}).get("pages", {}).values():
            item = (p.get("pageprops") or {}).get("wikibase_item")
            if item:
                orig = back.get(p["title"], p["title"])
                qid[orig.replace(" ", "_")] = item
                qid[p["title"].replace(" ", "_")] = item
        time.sleep(0.3)

    def claims(ids):
        out = {}
        ids = list(ids)
        for i in range(0, len(ids), 40):
            q = urllib.parse.urlencode({"action": "wbgetentities", "ids": "|".join(ids[i:i + 40]), "props": "claims|labels",
                                        "languages": "en", "format": "json"})
            out.update(json.loads(get(f"{WD}?{q}")).get("entities", {}))
            time.sleep(0.3)
        return out

    ents = claims(set(qid.values()))
    coord = lambda e: next((((c["mainsnak"].get("datavalue") or {}).get("value")) for c in e.get("claims", {}).get("P625", [])  # noqa: E731
                            if c["mainsnak"].get("datavalue")), None)
    hq = {}
    for q, e in ents.items():
        for c in e.get("claims", {}).get("P159", []):
            v = (c["mainsnak"].get("datavalue") or {}).get("value")
            if v and v.get("id"):
                hq[q] = v["id"]
                break
    places = claims(set(hq.values())) if hq else {}
    res = {}
    for t, q in qid.items():
        e = ents.get(q, {})
        if q in hq and places.get(hq[q]):
            pl = places[hq[q]]
            c = coord(pl)
            if c:
                res[t] = (c["longitude"], c["latitude"], "headquarters: " + ((pl.get("labels") or {}).get("en") or {}).get("value", hq[q]), q)
                continue
        c = coord(e)
        if c:
            res[t] = (c["longitude"], c["latitude"], "the company's own coordinates on Wikidata", q)
    return res


def main():
    OUT.mkdir(exist_ok=True)
    q = urllib.parse.urlencode({"action": "parse", "page": PAGE, "prop": "text", "format": "json", "formatversion": 2})
    html = json.loads(get(f"{WP}?{q}"))["parse"]["text"]
    p = Page()
    p.feed(html)
    rows_out, titles = [], set()
    for n, t in enumerate(p.tables):
        g = grid(t["rows"])
        head = [c for c in g[0]] if g else []
        names = [c["text"] or f"column {i + 1}" for i, c in enumerate(head)]
        ci = next((i for i, h in enumerate(names) if re.search(r"company|manufacturer|maker|producer", h, re.I)), None)
        if ci is None:
            continue
        for line in g[1:]:
            if all(c["th"] for c in line):
                continue
            rec = {"table": t["section"] or f"table {n + 1}"}
            for i, c in enumerate(line):
                k = names[i] if i < len(names) else f"column {i + 1}"
                if k in rec and rec[k] != c["text"]:
                    k = f"{k} ({i + 1})"
                rec[k] = c["text"]
            link = line[ci]["link"] if ci < len(line) else None
            if link:
                titles.add(link)
            rows_out.append((rec, link))
    places = wikidata_places(sorted(titles)) if titles else {}
    feats, unplaced = [], 0
    for rec, link in rows_out:
        pl = places.get(link) if link else None
        props = dict(rec)
        props["Wikipedia article"] = f"https://en.wikipedia.org/wiki/{link}" if link else ""
        if pl:
            props["Placed at"] = pl[2]
            props["Wikidata"] = f"https://www.wikidata.org/wiki/{pl[3]}"
            geom = {"type": "Point", "coordinates": [pl[0], pl[1]]}
        else:
            props["Placed at"] = "not placed: Wikidata gives no headquarters or coordinates" if link else "not placed: the row links no article"
            geom = None
            unplaced += 1
        feats.append({"type": "Feature", "properties": props, "geometry": geom})
    (OUT / "companies.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False))
    (OUT / "companies_build.json").write_text(json.dumps({"rows": len(feats), "unplaced": unplaced,
        "source": "Wikipedia, List of photovoltaics companies (CC BY-SA 4.0); headquarters from Wikidata (CC0)"}, indent=1))
    print(f"solar_companies: {len(feats)} rows, {unplaced} not placed")


if __name__ == "__main__":
    main()
