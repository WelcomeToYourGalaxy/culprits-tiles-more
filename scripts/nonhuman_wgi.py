#!/usr/bin/env python3
"""
How each country is governed, for the Culprits map's rows under
Biodiversity loss (round nh2, asked 16 October): the owner's page notes that
the countries richest in species tend to have lower governance scores
(footnote 19.7).

Source: the World Bank's Worldwide Governance Indicators (Kaufmann and Kraay),
from the World Bank's open data service (source 3), CC BY 4.0. Six measures.
Since the September 2025 revision the World Bank no longer publishes
percentile ranks (the old series, e.g. GE.PER.RNK, are archived); it
publishes a governance score from 0 (worst) to 100 (best) on a fixed scale,
with its 90% confidence bounds, beside the estimate itself (about -2.5 to
2.5). Each country's record holds every figure for every year; the map
shades by the newest year's score (round nh4).

  nonhuman/wgi.json, nonhuman/wgi.build.json

Weekly; WGI_REBUILD=1 or a run by hand builds at once.
"""
import pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
import nhcommon as nh  # noqa: E402

NAME = "wgi"
API = "https://api.worldbank.org/v2/country/all/indicator/GOV_WGI_{code}?source=3&format=json&per_page=20000"
# Names the service gives with no ISO code that the shared matcher misses.
EXTRA = {"Taiwan, China": ("TWN",), "Kosovo": ("XKX", "KOS", "XKO"), "Naoero": ("NRU",), "Monaco": ("MCO",), "Tuvalu": ("TUV",),
         "French Guiana": ("GUF",), "Martinique": ("MTQ",), "Reunion": ("REU",)}
KINDS = (("score", "SC"), ("low", "SC_LB"), ("high", "SC_UB"), ("estimate", "EST"))
MEASURES = [("va", "Voice and accountability", "VA"), ("pv", "Political stability and absence of violence", "PV"),
            ("ge", "Government effectiveness", "GE"), ("rq", "Regulatory quality", "RQ"), ("rl", "Rule of law", "RL"),
            ("cc", "Control of corruption", "CC")]


def series(code):
    j = nh.get_json(API.format(code=code), timeout=180)
    rows = j[1] if isinstance(j, list) and len(j) > 1 else []
    return [(r.get("countryiso3code"), r.get("country", {}).get("value"), int(r["date"]), r["value"]) for r in rows or [] if r.get("value") is not None]


def main():
    if not nh.due(NAME, 7, "WGI_REBUILD"):
        return
    C = nh.Countries()
    out, report, unplaced = {}, {}, set()
    for key, words, code in MEASURES:
        for kind, suffix in KINDS:
            try:
                s = series(f"{code}.{suffix}")
            except Exception as e:
                report[f"{code}.{suffix}"] = f"not read: {e}"[:200]
                continue
            report[f"{code}.{suffix}"] = len(s)
            newest = {}
            for iso, name, year, v in s:
                if iso not in C.codes:
                    iso = C.by_name(name) or next((c for c in EXTRA.get(name, ()) if c in C.codes), None)
                if not iso:
                    unplaced.add(name)
                    continue
                rec = out.setdefault(iso, {"name": name})
                # Every year in a table of its own; the newest score of each
                # measure as a figure the box shows (x_...).
                rec.setdefault(f"years_{key}", {}).setdefault(str(year), {})[kind] = round(float(v), 3)
                if kind == "score" and year >= newest.get(iso, 0):
                    newest[iso] = year
                    rec[f"x_{words.lower()}_score_0_to_100"] = round(float(v), 1)
                    rec[f"x_{words.lower()}_year"] = year
                    rec[f"{key}_score"] = round(float(v), 2)
    nh.write_json("wgi.json", out)
    nh.write_stamp(NAME, {"series read": report, "countries": len(out), "not placed (regions and groups)": sorted(x for x in unplaced if x)[:80],
                          "failed": not out})


if __name__ == "__main__":
    main()
