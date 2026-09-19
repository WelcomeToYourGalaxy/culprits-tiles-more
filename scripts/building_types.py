#!/usr/bin/env python3
"""
Building types: rebuilds tiles/building_types.pmtiles (and its summary,
tiles/building_types.json) from the accountability maps' building files, with
duplicate places merged, using the culprits repo's pipeline/building_types.py.
Weekly (Mondays), or when the workflow is run by hand, or when not yet built.
"""
import os, pathlib, shutil, subprocess, sys, tempfile, time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from mines import tools, sh, LIMIT  # noqa: E402  (the same tile tools)

OUT = pathlib.Path("tiles/building_types.pmtiles")
SUMMARY = pathlib.Path("tiles/building_types.json")


def main():
    weekly = time.gmtime().tm_wday == 0 or os.environ.get("GITHUB_EVENT_NAME", "workflow_dispatch") == "workflow_dispatch"
    if OUT.exists() and not weekly:
        print("building types: rebuilt weekly; not today")
        return
    tools()
    work = pathlib.Path(tempfile.mkdtemp())
    sh("git", "clone", "--depth", "1", "https://github.com/WelcomeToYourGalaxy/culprits.git", str(work / "culprits"))
    sh(sys.executable, "-m", "pip", "install", "-q", "requests")
    pts = work / "buildings.geojsonl"
    sh(sys.executable, str(work / "culprits/pipeline/building_types.py"), str(pts), str(SUMMARY.resolve()),
       cwd=str(work / "culprits/pipeline"))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = work / "building_types.pmtiles"
    for maxz in (14, 13, 12):
        sh("tippecanoe", "-o", str(tmp), "--force", "-Z0", f"-z{maxz}", "-l", "buildings", "-P",
           "--drop-densest-as-needed", "--extend-zooms-if-still-dropping", "-r1", str(pts))
        if tmp.stat().st_size <= LIMIT:
            break
    else:
        sys.exit("building types: could not get the archive under GitHub's 100 MB limit")
    shutil.move(str(tmp), str(OUT))
    print(f"building types: built {OUT} ({OUT.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
