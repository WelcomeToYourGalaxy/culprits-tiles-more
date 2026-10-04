#!/usr/bin/env python3
"""Climate TRACE by gas: nitrous oxide only (round 75). The same build as ct_gases.py,
run as a job of its own so nitrous oxide is built beside carbon dioxide rather than
after it. Sectors in the order the Destruction page names this gas's sources;
its list is tiles/climate_trace_gases_n2o.json."""
import os, pathlib, sys
os.environ["CT_GASES"] = "n2o"
os.environ.setdefault("CT_SECTORS", "agriculture,forestry_and_land_use,waste,power,manufacturing,transportation,buildings,fossil_fuel_operations")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import ct_gases  # noqa: E402

if __name__ == "__main__":
    ct_gases.main()
