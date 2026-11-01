"""Military places sorted by what they are, whichever source records them.

Written 30 September (round 118b). The owner found the military rows hard to
tell apart: Wikidata's installations, OpenStreetMap's military places and the
US Department of Defense's register each held bases, airfields and ranges, and
OpenStreetMap's held nuclear explosion sites its title did not name. Here the
places from all three (as military.py copies them each day) are sorted by what
each source says they are, into one file per kind:

  military/kinds/air.geojson      air bases and military airfields
  military/kinds/naval.geojson    naval bases and stations
  military/kinds/bases.geojson    bases, barracks, garrisons, armouries, depots
  military/kinds/ranges.geojson   firing ranges and training areas
  military/kinds/nuclear.geojson  nuclear explosion and test sites, missile launch facilities
  military/kinds/schools.geojson  military schools, academies and hospitals
  military/kinds/forts.geojson    castles, forts and other fortifications (mostly historic)
  military/kinds/other.geojson    everything else the sources file as military

Nothing is dropped: a place goes to the first kind whose words match the
source's own kind (Wikidata's kind, OpenStreetMap's military tag, the
register's name), and to "other" when none does. Every field the source gives
is kept, beside "source", "kind" (the source's own words), "status" (in use or
closed, as the source says) and, for the register, its codes in plain words.
The rules and the counts are in military/kinds/build.json.
"""
import json, pathlib, re, time

IN = pathlib.Path("military")
OUT = IN / "kinds"

KINDS = [  # (file, words in the source's kind or name)
    ("nuclear", r"nuclear|missile launch|missile silo|test site"),
    ("air", r"air ?base|airfield|fliegerhorst|air station|air force|royal air force|airport|aerodrome|air national guard|\bafb\b|\bang\b"),
    ("naval", r"naval|navy|submarine|dockyard|coast guard|marine corps|\bnas\b|\bnsa\b|sea base"),
    ("ranges", r"\brange\b|training area|training cent|proving ground|test range|firing|manoeuv|maneuver|polygon"),
    ("schools", r"academ|school|college|hospital|university"),
    ("forts", r"castle|fort|nuragh|wall|gate|tower|bastion|casemate|pillbox|bunker|redoubt|rampart|citadel|\bkeep\b|castr|oppid|\bdun\b|dava|\bgord\b|ksar|crannog|kremlin|stronghold|moat|sconce|enceinte|blockhouse|battery|trench|defen[cs]|burg|rocca|castell|\bpā\b|gusuku|\bborg\b|zwinger|motte|milecastle|acropolis|outpost|watch|landwehr|bailey|shelter|bergfried|bastle|lunette|diaolou|kasbah|alcazaba|alcázar|tenshu|dzong|presidio|tulou|ouvrage|tobruk|kazemat|turret|celtiberian|culă|strażnica|vigilarium"),
    ("bases", r"base|barracks|garrison|camp|cantonment|installation|armou?ry|arsenal|military building|depot|ammunition|magazine|drill hall|guardhouse|station|headquarters|command|reserve center|national guard"),
]
OSM_KIND = {"airfield": "air", "naval_base": "naval", "base": "bases", "barracks": "bases", "range": "ranges",
            "training_area": "ranges", "nuclear_explosion_site": "nuclear"}
WORDS = {
    "siteReportingComponent": {"usn": "US Navy", "armyNationalGuard": "Army National Guard", "usaf": "US Air Force", "usa": "US Army",
                               "airNationalGuard": "Air National Guard", "usar": "US Army Reserve", "usmc": "US Marine Corps",
                               "afr": "Air Force Reserve", "usmcr": "Marine Corps Reserve", "usnr": "Navy Reserve",
                               "whs": "Washington Headquarters Services (Defense Department offices)", "other": "other"},
    "siteOperationalStatus": {"act": "in use", "care": "kept in caretaker status, not in use", "clsd": "closed",
                              "excs": "surplus, to be given up", "semi": "partly in use"},
    "isFirrmaSite": {"Yes": "yes: foreign buyers of land near it are reviewed by the US government (FIRRMA)", "No": "no"},
    "isJointBase": {"Yes": "yes: shared by more than one service", "No": "no"},
    "isCui": {"Yes": "yes: controlled unclassified information", "No": "no"},
}
PLAIN = {"siteReportingComponent": "branch that runs it", "siteOperationalStatus": "status in the register",
         "isFirrmaSite": "foreign land purchases nearby reviewed", "isJointBase": "joint base", "isCui": "controlled information",
         "stateNameCode": "state", "countryName": "country", "siteName": "site", "featureName": "name in the register"}


def kind_of(text, skip=()):
    t = str(text or "").lower()
    for k, rx in KINDS:
        if k not in skip and re.search(rx, t):
            return k
    return "other"


def read(name):
    p = IN / name
    if not p.exists():
        print(f"military_kinds: {p} not there yet")
        return []
    return json.loads(p.read_text()).get("features", [])


def main():
    out = {k: [] for k, _ in KINDS}
    out["other"] = []
    counts = {}

    def put(kind, f, props):
        out[kind].append({"type": "Feature", "geometry": f["geometry"], "properties": props})
        counts.setdefault(props["source"], {}).setdefault(kind, 0)
        counts[props["source"]][kind] += 1

    for f in read("sites.geojson"):
        p = dict(f.get("properties") or {})
        k = kind_of(p.get("kind")) if p.get("kind") else kind_of(p.get("name"))
        closed = str(p.get("group", "")).startswith("closed")
        p.update({"source": "Wikidata", "status": "closed" if closed else "in use, or no closing recorded"})
        put(k, f, p)
    for f in read("osm_military.geojson"):
        p = dict(f.get("properties") or {})
        # The tag, or the kind its group names (a place no longer in use keeps it there).
        tag = str(p.get("military") or "")
        was = str(p.get("group") or "").replace(" (no longer in use)", "").replace(" ", "_")
        k = OSM_KIND.get(tag) or OSM_KIND.get(was) or kind_of(f"{tag} {was} {p.get('name', '')}")
        gone = "no longer" in str(p.get("group", ""))
        p.update({"source": "OpenStreetMap", "kind": str(p.get("group") or tag).replace(" (no longer in use)", ""),
                  "status": "no longer in use" if gone else "in use, or no end recorded"})
        put(k, f, p)
    for f in read("mirta.geojson"):
        raw = dict(f.get("properties") or {})
        p = {"name": raw.get("siteName") or raw.get("featureName")}
        for key, v in raw.items():
            if key in ("OBJECTID", "mediaId", "mirtaLocationsIdpk", "featureDescription") and str(v).strip() in ("", "NA"):
                continue
            p[PLAIN.get(key, key)] = WORDS.get(key, {}).get(v, v)
        p.update({"source": "US Department of Defense register (MIRTA)", "kind": "US military installation, range or training area",
                  "status": WORDS["siteOperationalStatus"].get(raw.get("siteOperationalStatus"), raw.get("siteOperationalStatus") or "")})
        # "Fort Bragg" is an installation, not an old fortification.
        k = kind_of(f"{raw.get('siteName', '')} {raw.get('featureName', '')}", skip=("forts",))
        put("bases" if k == "other" else k, f, p)
    for f in read("test_sites.geojson"):
        p = dict(f.get("properties") or {})
        p.update({"source": "Wikidata", "kind": "nuclear weapons test site",
                  "status": "closed" if str(p.get("group", "")).startswith("closed") else "in use, or no closing recorded"})
        put("nuclear", f, p)
    OUT.mkdir(parents=True, exist_ok=True)
    for k, feats in out.items():
        for ft in feats:
            pr = ft["properties"]
            pr["group"] = pr["status"]
            # Wikidata items with no English label come as their number (Q...):
            # named by their kind instead, the number kept in its own field.
            if re.fullmatch(r"Q\d+", str(pr.get("name") or "")):
                pr["wikidata item"] = pr["name"]
                pr["name"] = f"{pr.get('kind') or 'military place'} (no name in Wikidata)"
        (OUT / f"{k}.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False, separators=(",", ":")))
    (OUT / "build.json").write_text(json.dumps({"built": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
                                                "by_source_and_kind": counts, "files": {k: len(v) for k, v in out.items()},
                                                "rules": {k: rx for k, rx in KINDS}, "osm_tags": OSM_KIND}, indent=1))
    print("military_kinds:", {k: len(v) for k, v in out.items()})


if __name__ == "__main__":
    main()
