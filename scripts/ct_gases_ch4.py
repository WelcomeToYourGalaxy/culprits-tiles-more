#!/usr/bin/env python3
"""Climate TRACE by gas: methane only (round 75). The same build as ct_gases.py,
run as a job of its own so methane is built beside carbon dioxide rather than
after it. Sectors in the order the Destruction page names this gas's sources;
its list is tiles/climate_trace_gases_ch4.json."""
import os, pathlib, sys
os.environ["CT_GASES"] = "ch4"
os.environ.setdefault("CT_SECTORS", "agriculture,fossil_fuel_operations,waste,forestry_and_land_use,power,manufacturing,transportation,buildings")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import ct_gases  # noqa: E402

if __name__ == "__main__":
    ct_gases.main()
