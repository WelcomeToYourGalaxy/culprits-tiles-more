#!/usr/bin/env python3
"""
A daily copy of ESA's near-Earth-object risk list (NEO Coordination Centre),
neo/esa_risk_list.txt, exactly as ESA publishes it: every object with a
non-zero chance of striking Earth in the next hundred years, with its
diameter, the date of its likeliest impact, the chance of it, its Palermo and
Torino ratings, speed and years of possible impact. Culprits reads ESA's own
file first and this copy only if ESA's server will not let the page read it.

  https://neo.ssa.esa.int/PSDB-portlet/download?file=esa_risk_list
"""
import pathlib, sys, urllib.request

URL = "https://neo.ssa.esa.int/PSDB-portlet/download?file=esa_risk_list"
OUT = pathlib.Path("neo/esa_risk_list.txt")


def main():
    req = urllib.request.Request(URL, headers={"User-Agent": "Culprits atlas daily copy"})
    try:
        text = urllib.request.urlopen(req, timeout=120).read().decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        sys.exit(f"esa risk list: could not read ({e}); the last good copy stays")
    rows = [l for l in text.splitlines() if l.count("|") >= 10 and l[:4].strip() and not l.startswith(("Num/", "AAAA", "  "))]
    if "Last Update" not in text or not rows:
        sys.exit("esa risk list: the answer was not the list; the last good copy stays")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    print(f"esa risk list: {len(rows)} objects; {text.splitlines()[0].strip()}")


if __name__ == "__main__":
    main()
