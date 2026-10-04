#!/usr/bin/env python3
"""
Where nuclear weapons are stored, as the Nuclear Notebook states it (round 79,
27 September). No open dataset of these sites exists; this file writes down
what the Federation of American Scientists' Nuclear Notebook (Bulletin of the
Atomic Scientists) says, site by site, with the words quoted and the article
linked, and nothing else.

Positions: where the Notebook (or FAS, as the owner gave them) states
coordinates, those; otherwise the site's own coordinates in Wikidata, looked up
by its name at each run and linked in its box so the match can be checked. A
place the Notebook only says a depot is "near" is drawn at that town and says so.

Writes military/nuclear_sites.geojson.
"""
import json, pathlib, sys, time, urllib.parse, urllib.request

OUT = pathlib.Path("military/nuclear_sites.geojson")
UA = {"User-Agent": "Mozilla/5.0 (Culprits atlas daily copy; welcometoyourgalaxy@gmail.com)"}
EUROPE = "https://thebulletin.org/premium/2025-12/the-changing-nuclear-landscape-in-europe/"
US = "https://thebulletin.org/premium/2026-03/united-states-nuclear-weapons-2026/"
FAS = "https://fas.org/initiative/status-world-nuclear-forces/"

# name, country, Wikidata search words (None where coordinates are stated),
# stated [lat, lon] or None, what is stored as the source words it, source, status
SITES = [
    ("Aviano Air Base", "Italy", None, [46.0313, 12.5968], "an estimated 20 to 30 US B61-12 nuclear bombs", EUROPE, "stored"),
    ("Ghedi Air Base", "Italy", "Ghedi Air Base", None, "an estimated 10 to 15 US B61-12 nuclear bombs", EUROPE, "stored"),
    ("Incirlik Air Base", "Türkiye", "Incirlik Air Base", None, "an estimated 20 to 30 US B61-12 nuclear bombs", EUROPE, "stored"),
    ("Kleine Brogel Air Base", "Belgium", "Kleine Brogel Air Base", None,
     "approximately 10 to 15 US B61-12 nuclear bombs; 11 protective aircraft shelters equipped with a Weapons Storage and Security System (WS3), which includes an underground elevator-drive vault; maximum base capacity of 44 weapons", EUROPE, "stored"),
    ("Volkel Air Base", "Netherlands", "Volkel Air Base", None, "an estimated 10 to 15 US B61-12 nuclear bombs", EUROPE, "stored"),
    ("Büchel Air Base", "Germany", None, [50.1762, 7.0640], "an estimated 10 to 15 US B61-12 nuclear bombs", EUROPE, "stored"),
    ("RAF Lakenheath", "United Kingdom", None, [52.40816, 0.55868],
     "there are indications that nuclear bombs may have recently been shipped here; the base has undergone a significant upgrade to reactivate a nuclear mission, but the status of weapons at the base remains uncertain because of the unfinished construction", EUROPE, "uncertain"),
    ("Military depot near Asipovichy", "Belarus", "Asipovichy", None,
     "a military depot near Asipovichy in central Belarus is currently the most likely candidate for the storage of Russian nuclear weapons (drawn at the town: the depot is near it)", EUROPE, "likely"),
    ("Kirtland Underground Munitions and Maintenance Storage Complex", "United States (New Mexico)", "Kirtland Air Force Base", None,
     "the most nuclear weapons by far; most of the weapons here are retired weapons awaiting dismantlement", US, "stored"),
    ("Strategic Weapons Facility Pacific, Naval Base Kitsap", "United States (Washington)", "Naval Base Kitsap", None,
     "named among the US storage locations; ballistic missile submarine base", US, "stored"),
    ("F.E. Warren Air Force Base", "United States (Wyoming)", "Francis E. Warren Air Force Base", None, "ICBM base", US, "stored"),
    ("Malmstrom Air Force Base", "United States (Montana)", "Malmstrom Air Force Base", None, "ICBM base", US, "stored"),
    ("Minot Air Force Base", "United States (North Dakota)", "Minot Air Force Base", None, "ICBM base", US, "stored"),
    ("Whiteman Air Force Base", "United States (Missouri)", "Whiteman Air Force Base", None, "bomber base; named by the owner from the Nuclear Notebook", US, "stored"),
]


def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read()


def wikidata(words):
    """The first Wikidata item for these words that has coordinates (P625)."""
    j = json.loads(get("https://www.wikidata.org/w/api.php?action=wbsearchentities&format=json&language=en&limit=5&search=" + urllib.parse.quote(words)))
    for hit in j.get("search", []):
        e = json.loads(get(f"https://www.wikidata.org/wiki/Special:EntityData/{hit['id']}.json"))["entities"][hit["id"]]
        for c in e.get("claims", {}).get("P625", []):
            v = c.get("mainsnak", {}).get("datavalue", {}).get("value")
            if v:
                return hit["id"], hit.get("label", ""), [v["latitude"], v["longitude"]]
        time.sleep(0.5)
    return None, None, None


def main():
    feats, missing = [], []
    for name, country, search, at, stored, src, status in SITES:
        props = {"name": name, "country": country, "what the Nuclear Notebook says": stored, "status": status,
                 "source": src, "summary of all states' arsenals": FAS}
        if at:
            props["position"] = "coordinates as the Nuclear Notebook (FAS) states them"
        else:
            try:
                qid, label, at = wikidata(search)
            except Exception as e:  # noqa: BLE001
                qid, label, at = None, None, None
                print(f"  {name}: Wikidata did not answer ({e})", file=sys.stderr)
            if not at:
                missing.append(name)
                continue
            props["position"] = f"Wikidata's coordinates for {label} ({qid}); the Notebook gives none"
            props["wikidata"] = f"https://www.wikidata.org/wiki/{qid}"
        # Round 85b: no link to MISSILEMAP (another site), at the owner's word.
        props["group"] = {"stored": "weapons stored (estimated)", "uncertain": "weapons possibly shipped, status uncertain",
                          "likely": "most likely storage site"}[status]
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [at[1], at[0]]}, "properties": props})
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({"type": "FeatureCollection", "features": feats,
                               "source": "Federation of American Scientists, Nuclear Notebook (Bulletin of the Atomic Scientists)"}, ensure_ascii=False, indent=1))
    print(f"nuclear_sites: {len(feats)} sites" + (f"; not placed: {', '.join(missing)}" if missing else ""))


if __name__ == "__main__":
    main()
