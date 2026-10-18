#!/usr/bin/env python3
"""
Surveillance companies, their funders, and the countries they surveil or
supply (round 193o, asked 13 October). From Surveillance Watch's public API
(surveillancewatch.io/docs: "Our API provides access to the underlying data
that is used to provide the Surveillance Watch visualisations. This API
enables you to integrate our data with your own endpoints.").

Every endpoint is read whole and kept as it comes:

  surveillance/raw/<endpoint>.json   entities, entity-types, countries,
                                     cities, funders, financial-markets

and drawn from it:

  surveillance/entities.geojson   every entity at its headquarters city
                                  (else its headquarters country), every
                                  field the API gives, rich text as text
  surveillance/links.geojson      a line from each entity to each country
                                  or entity it is listed as surveilling or
                                  providing to
  surveillance/build.json

Weekly (Mondays) or by hand.
"""
import datetime, json, math, os, pathlib, time, urllib.error, urllib.request

BASE = "https://www.surveillancewatch.io/api/v1/"
ENDPOINTS = ["entities", "entity-types", "countries", "cities", "funders", "financial-markets"]
OUT = pathlib.Path("surveillance")
UA = {"User-Agent": "WelcomeToYourGalaxy Culprits map (welcometoyourgalaxy@gmail.com)", "Accept": "application/json"}
CREDIT = "Surveillance Watch (surveillancewatch.io), through its public API"


def get(url):
    for i in range(6):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(15 * (i + 1))
                continue
            raise
    raise RuntimeError(f"rate limited at {url}")


def read_all(ep):
    """Every record of one endpoint, following pages where the answer has them."""
    out, page = [], 1
    while True:
        url = BASE + ep + (f"?page={page}" if page > 1 else "")
        j = get(url)
        if isinstance(j, list):
            return j
        items = j.get("items", j.get("docs", j.get("data")))
        if items is None:
            return [j]
        out += items
        more = j.get("hasNextPage") or (j.get("totalPages") and page < j["totalPages"]) or (j.get("nextPage") not in (None, False))
        if not more or not items or page > 500:
            return out
        page += 1
        time.sleep(1)


def text(node):
    """Lexical rich text -> plain text, paragraphs kept apart."""
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return "".join(text(n) for n in node)
    if isinstance(node, dict):
        if "root" in node:
            return text(node["root"]).strip()
        t = node.get("text", "")
        kids = text(node.get("children"))
        sep = "\n\n" if node.get("type") in ("paragraph", "heading", "listitem", "quote") else ""
        return t + kids + sep
    return str(node)


def label(v, lookup=None):
    """A record, an id or a list of them -> names."""
    if v is None:
        return ""
    if isinstance(v, list):
        return "; ".join(x for x in (label(i, lookup) for i in v) if x)
    if isinstance(v, dict):
        name = v.get("name") or v.get("title") or v.get("label")
        url = v.get("url") or v.get("link") or v.get("href")
        if name and url:
            return f"{name} ({url})"
        return str(name or url or v.get("domain") or v.get("value") or v.get("slug") or v.get("id") or "")
    if lookup is not None and v in lookup:
        return str(lookup[v].get("name") or v)
    return str(v)


def flat(v):
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    if isinstance(v, dict) and "root" in v:
        return text(v)
    return json.dumps(v, ensure_ascii=False)


def main():
    stamp = OUT / "build.json"
    if stamp.exists() and datetime.date.today().weekday() != 0 and os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch" \
            and not json.loads(stamp.read_text()).get("failed"):
        print("surveillance_watch: weekly; not Monday")
        return
    (OUT / "raw").mkdir(parents=True, exist_ok=True)
    status, data = {"read": datetime.date.today().isoformat(), "source": CREDIT, "endpoints": {}}, {}
    for ep in ENDPOINTS:
        try:
            data[ep] = read_all(ep)
            (OUT / "raw" / f"{ep}.json").write_text(json.dumps(data[ep], ensure_ascii=False))
            status["endpoints"][ep] = len(data[ep])
        except Exception as e:  # noqa: BLE001
            status["endpoints"][ep] = f"not read: {type(e).__name__}: {e}"[:300]
            old = OUT / "raw" / f"{ep}.json"
            data[ep] = json.loads(old.read_text()) if old.exists() else []
            status.setdefault("failed", []).append(ep)
    if not data["entities"]:
        stamp.write_text(json.dumps(status, indent=1, ensure_ascii=False))
        raise SystemExit("surveillance_watch: no entities read; see surveillance/build.json")
    by_id = {ep: {r.get("id"): r for r in data[ep] if isinstance(r, dict)} for ep in ENDPOINTS}
    countries, cities, ents = by_id["countries"], by_id["cities"], by_id["entities"]

    def ll(rec):
        if isinstance(rec, dict) and rec.get("latitude") is not None and rec.get("longitude") is not None:
            return float(rec["longitude"]), float(rec["latitude"])
        return None

    def resolve(v, table):
        return v if isinstance(v, dict) else table.get(v)

    def hq(e):
        city = resolve(e.get("headquartersCity"), cities)
        if ll(city):
            return ll(city), f"its headquarters city, {label(city)}"
        ctry = resolve(e.get("headquarters"), countries)
        if ll(ctry):
            return ll(ctry), f"the point Surveillance Watch gives for its headquarters country, {label(ctry)} (no city given)"
        return None, ""

    feats, links, spin, unplaced, types = [], [], {}, [], by_id["entity-types"]
    for e in data["entities"]:
        at, how = hq(e)
        props = {"name": e.get("name"), "kinds": label(e.get("types"), types),
                 "headquarters country": label(resolve(e.get("headquarters"), countries) or e.get("headquarters")),
                 "headquarters city": label(resolve(e.get("headquartersCity"), cities) or e.get("headquartersCity")),
                 "surveilling": label(e.get("surveilling"), countries), "providing to": label(e.get("providingTo"), countries),
                 "has direct targets": e.get("hasDirectTargets"), "funders": label(e.get("funders"), by_id["funders"]),
                 "funding": e.get("fundingType"), "also known as": label(e.get("alsoKnownAs")),
                 "affiliations": label(e.get("affiliations") or e.get("affiliationsList"), ents), "subsidiaries": label(e.get("subsidiaries"), ents),
                 "description": text(e.get("description")).strip(), "web domains": label(e.get("domains")),
                 "sources": label(e.get("sources")), "market": flat(e.get("marketInfo")), "other data": flat(e.get("otherData")),
                 "updated": e.get("updatedAt"), "Surveillance Watch page": f"https://www.surveillancewatch.io{e['path']}" if e.get("path") else ""}
        props = {k: v for k, v in props.items() if v not in (None, "", [])}
        if not at:
            unplaced.append(e.get("name"))
            continue
        key = f"{at[0]:.3f},{at[1]:.3f}"
        i = spin[key] = spin.get(key, -1) + 1
        ang, rad = math.radians(137.508 * i), 0.04 * math.sqrt(i)
        x = at[0] + rad * math.cos(ang) / max(0.3, math.cos(math.radians(at[1])))
        y = max(-85, min(85, at[1] + rad * math.sin(ang)))
        props["placed at"] = how + ("; spread so each can be clicked" if i else "")
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(x, 5), round(y, 5)]}, "properties": props})
        for field, word in (("surveilling", "surveilling"), ("providingTo", "providing to")):
            for t in (e.get(field) or []):
                rec = resolve(t, countries) or resolve(t, ents)
                end = ll(rec) or (hq(rec)[0] if isinstance(rec, dict) and rec in data["entities"] else None)
                if not end:
                    continue
                links.append({"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[round(x, 4), round(y, 4)], [round(end[0], 4), round(end[1], 4)]]},
                              "properties": {"entity": e.get("name"), "link": word, "to": label(rec), "kinds": props.get("kinds", "")}})
    OUT.mkdir(exist_ok=True)
    (OUT / "entities.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False))
    (OUT / "links.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": links}, ensure_ascii=False))
    first = data["entities"][0] if data["entities"] else {}
    status.update({"entities placed": len(feats), "not placed": unplaced, "links": len(links),
                   "entity fields seen": sorted(first.keys()) if isinstance(first, dict) else [],
                   "surveilling, first entity, as given": json.dumps(first.get("surveilling"))[:300] if isinstance(first, dict) else ""})
    stamp.write_text(json.dumps(status, indent=1, ensure_ascii=False))
    print(f"surveillance_watch: {len(feats)} entities placed, {len(unplaced)} not; {len(links)} links")


if __name__ == "__main__":
    main()
