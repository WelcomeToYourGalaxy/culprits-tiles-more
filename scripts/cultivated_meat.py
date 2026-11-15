#!/usr/bin/env python3
"""
Meat grown from cells: where it is banned, restricted or being considered
(round 140b, asked 2 October: "confirm the layer is complete ... US states in
the process or at least considering; maybe add regions simply considering
it").

Reads the abattoir atlas's own list (abattoir-atlas cultivated_meat_laws.json)
and adds the US states found since it was checked (16 September 2026) that
were missing from it, each with what was found and the source it was read
from. Nothing in the atlas's list is changed or dropped.

  cultivated/laws.json        the atlas's list with the additions, the same
                              shape (countries, us_states, statuses, sources);
                              the map's country layer reads it
  cultivated/us_states.geojson  each US state with an entry, its own outline
                              (cgaz-boundaries USA), shaded by status, with
                              every line of its entry
  cultivated/build.json       counts, and states named but not found in the
                              outlines

Weekly (Sundays), or by hand.
"""
import datetime, json, os, pathlib, sys, urllib.request
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

ATLAS = "https://raw.githubusercontent.com/WelcomeToYourGalaxy/abattoir-atlas/main/cultivated_meat_laws.json"
CGAZ = "https://raw.githubusercontent.com/WelcomeToYourGalaxy/cgaz-boundaries/main/USA.geojson"
OUT = pathlib.Path("cultivated")
UA = {"User-Agent": "Culprits atlas build (welcometoyourgalaxy@gmail.com)"}
STATE_NAMES = {"AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado", "CT": "Connecticut",
               "DE": "Delaware", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa",
               "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan",
               "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire",
               "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
               "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee",
               "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming"}
# Found 2 October 2026; each from the source named with it. "proposed" = a
# bill introduced and not passed as far as found; the last step found is said.
ADDED = [
    {"code": "IL", "status": "proposed", "what": "HB 0015, the Illinois Cultivated Meat Act, would prohibit the manufacture, sale and distribution of cultivated meat. Introduced; not passed as far as found.",
     "source": "CSG Midwest, 'Cell-cultured meat remains focus of new laws and legislation across the Midwest', updated 4 May 2026"},
    {"code": "MI", "status": "proposed", "what": "HB 4083 would prohibit the sale of cultivated meat. Introduced 12 February 2025; carried over into 2026.",
     "source": "CSG Midwest, 'Cell-cultured meat remains focus of new laws and legislation across the Midwest', updated 4 May 2026"},
    {"code": "ND", "status": "proposed", "what": "A 2025 bill (HB 1151) to prohibit in-state production and sale of cultivated meat. Not among the states with a ban as of 2026.",
     "source": "CSG Midwest, 4 May 2026; Brooks Institute Animal Law Digest, issue 276"},
    {"code": "OH", "status": "proposed", "what": "A 2025 bill to prohibit in-state production and sale of cultivated meat. Not among the states with a ban as of 2026.",
     "source": "CSG Midwest, 'Cell-cultured meat remains focus of new laws and legislation across the Midwest', updated 4 May 2026"},
    {"code": "WI", "status": "proposed", "what": "AB 554 would have restricted sales of lab-grown meat unless labelled and barred schools and other state institutions from serving it. Vetoed by Governor Tony Evers.",
     "source": "CSG Midwest, 'Cell-cultured meat remains focus of new laws and legislation across the Midwest', updated 4 May 2026"},
    {"code": "AZ", "status": "proposed", "what": "HB 2791 (2026) would make selling cell-cultured protein for human consumption a crime (up to 18 months in prison); HB 2672 would require a label. Introduced; outcome not found.",
     "source": "Arizona Capitol Times, 'Arizona may become first state to ban lab-grown meat', 20 January 2026"},
    {"code": "WV", "status": "proposed", "what": "HB 4462 (2026) would ban the manufacture and sale of cell-cultured food products; passed the House Government Organization Committee on 9 February 2026. Outcome not found.",
     "source": "West Virginia Watch (States Newsroom), 'Effort to ban lab-grown meat ... underway in WV House', 10 February 2026"},
    {"code": "TN", "status": "proposed", "what": "A proposed ban was shelved in 2024 after lawmakers argued it would restrict consumers' choices.",
     "source": "Stateline, 'Lab-grown meat isn't on store shelves yet, but some states have already banned it', 2024 (Brookings Register)"},
    {"code": "IA", "status": "partial", "what": "A 2024 law bars schools from buying lab-grown meat.",
     "source": "Stateline, 'Lab-grown meat isn't on store shelves yet, but some states have already banned it', 2024 (Brookings Register)"},
]
COLOURS = {"ban": "#0C2E5E", "temporary": "#1A5C92", "partial": "#46AACB", "proposed": "#9CD6E6"}


def get(url):
    return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120).read())


def main():
    if (OUT / "laws.json").exists() and datetime.date.today().weekday() != 6 and os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
        print("cultivated_meat: weekly; not Sunday")
        return
    d = get(ATLAS)
    have = {s["code"] for s in d.get("us_states", [])}
    added = [a for a in ADDED if a["code"] not in have]
    d["us_states"] = list(d.get("us_states", [])) + added
    d["sources"] = list(d.get("sources", [])) + sorted({a["source"] for a in added})
    d["note"] = (d.get("note", "") + " Round 140b of the map (2 October 2026) added US states found since this list was checked, each with its source; "
                 "'proposed' there means a bill introduced and not passed as far as found.")
    OUT.mkdir(exist_ok=True)
    (OUT / "laws.json").write_text(json.dumps(d, ensure_ascii=False, indent=1))
    from attacks_plain import rounded
    shapes = {f["properties"].get("shapeName"): f["geometry"] for f in get(CGAZ)["features"]}
    statuses = d.get("statuses", {})
    feats, missing = [], []
    for s in d["us_states"]:
        name = STATE_NAMES.get(s["code"], s["code"])
        g = shapes.get(name)
        if not g:
            missing.append(s["code"])
            continue
        st = statuses.get(s["status"], {})
        p = {"name": name, "group": st.get("label", s["status"]), "status": st.get("label", s["status"]), "what": s.get("what", ""),
             "_map_colour": COLOURS.get(s["status"], "#77726A")}
        if s.get("caveat"):
            p["caveat"] = s["caveat"]
        p["source"] = s.get("source") or "the abattoir atlas list (" + "; ".join(d.get("sources", [])[:3]) + ")"
        feats.append({"type": "Feature", "geometry": rounded(g, 3, 0.01), "properties": p})
    (OUT / "us_states.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False))
    (OUT / "build.json").write_text(json.dumps({"read": datetime.date.today().isoformat(), "atlas_checked": d.get("checked"), "states": len(feats),
                                                "added": [a["code"] for a in added], "not_found_in_outlines": missing}, indent=1))
    print(f"cultivated_meat: {len(feats)} states ({len(added)} added); not found: {missing}", flush=True)


if __name__ == "__main__":
    main()
