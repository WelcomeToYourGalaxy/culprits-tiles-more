"""Round 123b (asked 2 October: the environmental law layers all 404).
The three rows were drawn from files the map's old pipeline made once and
then stopped making. They are now made here, daily, from the enviro-atlas
repo's own index (WelcomeToYourGalaxy/enviro-atlas, atlas_index.json), which
is built from FAOLEX, FAO's database of national laws and policies.

envlaw/jurisdictions.geojson  one point per country, state or province the
                              index places, with how many instruments it holds,
                              their years and their commonest subjects, and a
                              link to its full list (atlas_data/<id>.json)
envlaw/countries.json         the national ones by ISO3, for country shading
envlaw/build.json             counts, and the "no jurisdiction / global"
                              instruments the index cannot place (said, not drawn)
"""
import json, pathlib, urllib.request, datetime

RAW = "https://raw.githubusercontent.com/WelcomeToYourGalaxy/enviro-atlas/main/"
OUT = pathlib.Path("envlaw")
UA = {"User-Agent": "Culprits atlas build (WelcomeToYourGalaxy)"}


def main():
    with urllib.request.urlopen(urllib.request.Request(RAW + "atlas_index.json", headers=UA), timeout=300) as r:
        idx = json.loads(r.read())
    feats, countries, unplaced = [], {}, []
    for j in idx:
        props = {"name": j.get("name"), "country": j.get("country"),
                 "level": {"nat": "Country", "sub": "State, province or region"}.get(j.get("level"), j.get("level")),
                 "instruments": j.get("count"),
                 "first_year": (j.get("years") or [None, None])[0], "latest_year": (j.get("years") or [None, None])[-1],
                 "full_list": RAW + "atlas_data/" + j["id"] + ".json"}
        for k, v in (j.get("sectors") or {}).items():
            props[f"Instruments on {k}"] = v
        if j.get("level") == "global" or j.get("lat") is None:
            unplaced.append({k: props[k] for k in ("name", "instruments", "first_year", "latest_year", "full_list")})
            continue
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [j["lon"], j["lat"]]}, "properties": props})
        if j.get("level") == "nat" and j.get("iso3"):
            countries[j["iso3"]] = {f"x_{k}": v for k, v in props.items() if k not in ("level",)}
    OUT.mkdir(exist_ok=True)
    (OUT / "jurisdictions.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False))
    (OUT / "countries.json").write_text(json.dumps(countries, ensure_ascii=False))
    (OUT / "build.json").write_text(json.dumps({"from": RAW + "atlas_index.json", "jurisdictions": len(feats), "countries": len(countries),
                                                "instruments": sum(j.get("count") or 0 for j in idx), "not_placed": unplaced,
                                                "read": datetime.date.today().isoformat()}, indent=1))
    print(f"envlaw: {len(feats)} jurisdictions, {len(countries)} countries; not placed: {unplaced}")


if __name__ == "__main__":
    main()
