#!/usr/bin/env python3
"""
Deletes the files this repo publishes but the map no longer reads.

A published GitHub Pages site is capped at 1 GB. This repo had grown to about
1,640 MB, most of it files nothing asks for:

  * the building archives (tiles/buildings/, tiles/building_types.json), which
    now live in culprits-buildings and are rebuilt there;
  * the archives of rows taken off the layers box - the Money, Legal and
    Activist building rows, whose records all went into Buildings, and the law
    and government shape layers removed on 19 and 20 September.

Nothing here is a source. Every file listed is built from data held elsewhere
and can be rebuilt: the building archives by culprits-buildings, the shapes by
culprits/pipeline/shapes/build_shapes.py (name the layer on the command line -
they are marked retired, so a plain run skips them), the pmtiles by the
culprits pipeline that made them.

Runs with the rest of the daily jobs. After the first run it finds nothing and
says so, which is what it should do; it stays in place so that a shape layer
rebuilt by an older copy of the builder does not creep back.
"""
import pathlib

# Moved to culprits-buildings.
MOVED = ["tiles/buildings", "tiles/building_types.json", "tiles/building_types.pmtiles"]

# Rows no longer in the layers box. Each name covers tiles/<name>.pmtiles,
# shapes/<name>.geojson and shapes/<name>.details.json.
RETIRED = [
    # Money, Legal and Activist building rows, now merged into Buildings.
    "fin_bank", "fin_centralbank", "fin_taxoffice", "fin_govfinance", "fin_financial",
    "fin_exchange", "fin_insurance", "fin_accountant", "fin_remittance", "fin_stockexchange",
    "fin_auditoffice", "fin_devbank", "fin_mint",
    "activist_police", "activist_courts", "activist_prisons",
    "slavery_facilities",
    # Law, government and site maps removed on 19 and 20 September.
    "enviro_law_by_country", "site_environment_law", "site_environment_law_shapes",
    "leg_laws", "leg_by_state", "leg_subnational", "leg_county", "leg_municipal",
    "leg_municipal_recover", "legal_by_state", "judicial_by_state",
    "gov_official_map", "site_export_credit_shading", "slavery_trackers",
    # Taken off the map after it was built.
    "love_trackers", "love_guides",
    "site_cartel_cells", "site_self_sufficiency", "site_subsistence_cultures", "site_ufo_pre1900",
]


def targets():
    for p in MOVED:
        yield pathlib.Path(p)
    for name in RETIRED:
        yield pathlib.Path(f"tiles/{name}.pmtiles")
        yield pathlib.Path(f"shapes/{name}.geojson")
        yield pathlib.Path(f"shapes/{name}.details.json")


def main():
    freed = 0
    gone = []
    for path in targets():
        if not path.exists():
            continue
        if path.is_dir():
            size = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
            for f in sorted(path.rglob("*"), reverse=True):
                f.unlink() if f.is_file() else f.rmdir()
            path.rmdir()
        else:
            size = path.stat().st_size
            path.unlink()
        freed += size
        gone.append(f"  {path} ({size / 1e6:.1f} MB)")
    if not gone:
        print("retire: nothing left to remove")
        return
    print("\n".join(gone))
    print(f"retire: {len(gone)} removed, {freed / 1e6:.0f} MB freed")


if __name__ == "__main__":
    main()
