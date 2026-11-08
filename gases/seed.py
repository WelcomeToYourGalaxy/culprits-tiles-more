#!/usr/bin/env python3
"""
Round 110b: fills culprits-tiles-gases, once, with the by-gas Climate TRACE
archives already built in culprits-tiles-more, read from that repository as it
was at commit SOURCE (before they were deleted there), so nothing is built
twice. Pushed in batches, since GitHub takes at most 2 GB in one push. Does
nothing once tiles/climate_trace_gases.json is here.
"""
import os, pathlib, re, shutil, subprocess, sys, tempfile, time, urllib.request

SOURCE = "64ba5fd0f3bc4189f825526e282f8c7d8de66382"
MORE = "https://github.com/WelcomeToYourGalaxy/culprits-tiles-more.git"
RAW = f"https://raw.githubusercontent.com/WelcomeToYourGalaxy/culprits-tiles-more/{SOURCE}/"
WANT = re.compile(r"^(tiles/climate_trace_(co2|ch4|n2o)_[^/]+|tiles/climate_trace_gases[^/]*\.json|climate_gases/[^/]+)$")
BATCH = 14          # archives are at most 95 MB, so a batch stays under 1.4 GB


def sh(*cmd, **kw):
    print("  $", " ".join(cmd), flush=True)
    return subprocess.run(cmd, check=True, **kw)


def push(msg):
    sh("git", "add", "-A")
    if subprocess.run(["git", "diff", "--cached", "--quiet"]).returncode == 0:
        return
    sh("git", "commit", "-q", "-m", msg)
    for i in range(8):
        if subprocess.run(["git", "push", "-q", "origin", "HEAD:main"]).returncode == 0:
            return
        subprocess.run(["git", "pull", "-q", "--rebase", "-X", "theirs", "origin", "main"])
        time.sleep(10 + 5 * i)
    sys.exit("seed: could not push")


def main():
    if pathlib.Path("tiles/climate_trace_gases.json").exists():
        print("seed: already filled")
        return
    for d in ("/usr/share/dotnet", "/usr/local/lib/android", "/opt/ghc", "/opt/hostedtoolcache/CodeQL"):
        subprocess.run(["sudo", "rm", "-rf", d])
    sh("git", "config", "user.name", "culprits-refresh")
    sh("git", "config", "user.email", "actions@users.noreply.github.com")
    src = pathlib.Path(tempfile.mkdtemp())
    sh("git", "init", "-q", str(src))
    sh("git", "-C", str(src), "fetch", "-q", "--depth", "1", "--filter=blob:none", MORE, SOURCE)
    names = sh("git", "-C", str(src), "ls-tree", "-r", "--name-only", "FETCH_HEAD", capture_output=True, text=True).stdout.split()
    files = sorted(n for n in names if WANT.match(n))
    # The lists last, so a run stopped halfway starts again.
    files.sort(key=lambda n: n.startswith("tiles/climate_trace_gases"))
    print(f"seed: {len(files)} files from culprits-tiles-more at {SOURCE[:7]}", flush=True)
    pathlib.Path(".nojekyll").touch()
    done = 0
    for i in range(0, len(files), BATCH):
        for n in files[i:i + BATCH]:
            p = pathlib.Path(n)
            if p.exists():
                continue
            p.parent.mkdir(parents=True, exist_ok=True)
            for t in range(4):
                try:
                    with urllib.request.urlopen(RAW + n, timeout=600) as r, open(p, "wb") as f:
                        shutil.copyfileobj(r, f)
                    break
                except Exception as e:  # noqa: BLE001
                    print(f"  {n}: {e}; again", flush=True)
                    time.sleep(10)
            else:
                sys.exit(f"seed: could not read {n}")
            done += 1
        push(f"Seed from culprits-tiles-more, files {i + 1} to {min(i + BATCH, len(files))} of {len(files)}")
    subprocess.run(["gh", "api", "-X", "POST", f"repos/{os.environ.get('REPO', '')}/pages/builds"])
    print(f"seed: {done} files copied")


if __name__ == "__main__":
    main()
