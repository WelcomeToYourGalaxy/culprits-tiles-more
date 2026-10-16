#!/usr/bin/env python3
"""
How each country is governed, for the Culprits map's rows under
Biodiversity loss (round nh2, asked 16 October): the owner's page notes that
the countries richest in species tend to have lower governance scores
(footnote 19.7).

Source: the World Bank's Worldwide Governance Indicators (Kaufmann and Kraay),
from the World Bank's open data service (source 3), CC BY 4.0. Six measures,
each as a percentile rank among all countries (0 the lowest, 100 the
highest) and as the estimate itself (about -2.5 to 2.5), every year given.
Each country's record holds every figure; the map shades by the newest year's
percentile rank.

  nonhuman/wgi.json, nonhuman/wgi.build.json

Weekly; WGI_REBUILD=1 or a run by hand builds at once.
"""
import pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
import nhcommon as nh  # noqa: E402

NAME = "wgi"
API = "https://api.worldbank.org/v2/country/all/indicator/{code}?source=3&format=json&per_page=20000"
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
    out, report = {}, {}
    for key, words, code in MEASURES:
        for kind, suffix in (("rank", "PER.RNK"), ("estimate", "EST")):
            try:
                s = series(f"{code}.{suffix}")
            except Exception as e:
                report[f"{code}.{suffix}"] = f"not read: {e}"[:200]
                continue
            report[f"{code}.{suffix}"] = len(s)
            newest = {}
            for iso, name, year, v in s:
                if iso not in C.codes:
                    continue
                rec = out.setdefault(iso, {"name": name})
                # Every year in a table of its own; the newest rank of each
                # measure as a figure the box shows (x_...).
                rec.setdefault(f"years_{key}", {}).setdefault(str(year), {})[kind] = round(float(v), 3)
                if kind == "rank" and year >= newest.get(iso, 0):
                    newest[iso] = year
                    rec[f"x_{words.lower()}_percentile_rank"] = round(float(v), 2)
                    rec[f"x_{words.lower()}_year"] = year
                    rec[f"{key}_rank"] = round(float(v), 2)
    nh.write_json("wgi.json", out)
    nh.write_stamp(NAME, {"series read": report, "countries": len(out), "failed": not out})


if __name__ == "__main__":
    main()
