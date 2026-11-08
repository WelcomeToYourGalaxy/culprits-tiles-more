#!/usr/bin/env python3
"""
The site's own maps' shapes, kept in step with the maps themselves.

shapes/<id>.geojson and shapes/<id>.details.json (the shaded countries, lines
and per-country lists of the site's maps, such as the Drug underworld and
capture map) were built once and uploaded by hand, so an edit to one of those
maps never reached the Culprits map. This rebuilds them every day from each
map's current page, with the culprits repo's own builder
(pipeline/shapes/build_shapes.py), and puts them where the Culprits map reads
them. Only files that actually changed are committed.

A map that fails to build keeps its last copy; the others still update.
"""
import pathlib, shutil, subprocess, sys, tempfile

OUT = pathlib.Path("shapes")


def sh(*cmd, **kw):
    print("  $", " ".join(cmd), flush=True)
    return subprocess.run(cmd, **kw)


def main():
    work = pathlib.Path(tempfile.mkdtemp())
    repo = work / "culprits"
    if sh("git", "clone", "--depth", "1", "https://github.com/WelcomeToYourGalaxy/culprits.git", str(repo)).returncode:
        sys.exit("site shapes: could not fetch the culprits repo")
    sh(sys.executable, "-m", "pip", "install", "-q", "requests")
    built = repo / "map" / "data" / "shapes"
    # Start empty, so only what this run built is copied across.
    if built.exists():
        shutil.rmtree(built)
    run = sh(sys.executable, str(repo / "pipeline" / "shapes" / "build_shapes.py"), cwd=str(repo))
    if not built.exists() or not any(built.glob("*.geojson")):
        sys.exit("site shapes: nothing was built; the last copies stay")
    OUT.mkdir(exist_ok=True)
    n = 0
    for f in sorted(built.iterdir()):
        if f.suffix == ".json" or f.suffix == ".geojson":
            shutil.copy2(f, OUT / f.name)
            n += 1
    print(f"site shapes: {n} files copied into {OUT}/" + ("" if run.returncode == 0 else " (some maps did not build; their last copies stay)"))


if __name__ == "__main__":
    main()
