#!/usr/bin/env python3
"""
A look at the two sources a deforestation-funds layer would be built from, so
the builder can be written against what they really hold (26 September):

  SEC Form N-PORT data sets: every US-registered fund's holdings, quarterly,
  public (https://www.sec.gov/data-research/sec-markets-data/form-n-port-data-sets).
  Saved to probe/nport/: the latest quarter's file list, each table's columns
  and row count, and the first 25 rows of each table.

  Forest 500 (Global Canopy, CC BY-NC 4.0): the companies and financial
  institutions it assesses for deforestation risk. Saved to probe/forest500/:
  every link on its rankings and data pages that points at a data file, and
  those files themselves when they are spreadsheets or CSVs.

Nothing is published to the map from this. Runs once; it does nothing when
its files are already there (DEFOR_PROBE_AGAIN=1 reads again).
"""
import csv, io, json, os, pathlib, re, sys, time, urllib.parse, urllib.request, zipfile

NPORT_PAGE = "https://www.sec.gov/data-research/sec-markets-data/form-n-port-data-sets"
F500_PAGES = ["https://forest500.org/data", "https://forest500.org/rankings/companies",
              "https://forest500.org/rankings/financial-institutions", "https://forest500.org/forest-500-data-methods/"]
OUT = pathlib.Path("probe")
# The SEC asks automated readers to name themselves.
UA = {"User-Agent": "WelcomeToYourGalaxy Culprits map github.com/WelcomeToYourGalaxy", "Accept-Encoding": "identity"}


def get(url, tries=5, timeout=600):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            if i == tries - 1:
                raise
            print(f"    {url}: {e}; again in {30 * (i + 1)}s", flush=True)
            time.sleep(30 * (i + 1))


def nport():
    d = OUT / "nport"
    if (d / "tables.json").exists() and not os.environ.get("DEFOR_PROBE_AGAIN"):
        print("  N-PORT: already read")
        return
    d.mkdir(parents=True, exist_ok=True)
    page = get(NPORT_PAGE).decode("utf-8", "replace")
    zips = sorted(set(re.findall(r'/files/dera/data/form-n-port-data-sets/(\d{4}q\d)_nport\.zip', page)))
    (d / "quarters.json").write_text(json.dumps(zips, indent=1))
    if not zips:
        sys.exit("N-PORT: no quarterly files found on the SEC's page")
    q = zips[-1]
    path = pathlib.Path("/tmp") / f"{q}_nport.zip"
    if not path.exists():
        print(f"  N-PORT: downloading {q}", flush=True)
        path.write_bytes(get(f"https://www.sec.gov/files/dera/data/form-n-port-data-sets/{q}_nport.zip", timeout=1800))
    tables = {"quarter": q, "tables": {}}
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            info = {"bytes": z.getinfo(name).file_size}
            if name.lower().endswith((".tsv", ".txt", ".csv")):
                with z.open(name) as f:
                    text = io.TextIOWrapper(f, encoding="utf-8", errors="replace")
                    head = text.readline().rstrip("\n")
                    delim = "\t" if "\t" in head else ","
                    info["columns"] = head.split(delim)
                    sample, n = [], 0
                    for line in text:
                        n += 1
                        if n <= 25:
                            sample.append(line.rstrip("\n").split(delim))
                    info["rows"] = n
                (d / f"{pathlib.Path(name).stem}.sample.json").write_text(json.dumps(sample))
            tables["tables"][name] = info
            print(f"  N-PORT {name}: {info.get('rows', '?')} rows", flush=True)
    (d / "tables.json").write_text(json.dumps(tables, indent=1))


def forest500():
    d = OUT / "forest500"
    if (d / "links.json").exists() and not os.environ.get("DEFOR_PROBE_AGAIN"):
        print("  Forest 500: already read")
        return
    d.mkdir(parents=True, exist_ok=True)
    links = {}
    for page in F500_PAGES:
        try:
            html = get(page, tries=3).decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            links[page] = {"error": str(e)}
            continue
        found = sorted(set(urllib.parse.urljoin(page, h) for h in re.findall(r'href="([^"]+)"', html)
                           if re.search(r"\.(xlsx?|csv|zip|json)(\?|$)|download|export", h, re.I)))
        links[page] = found
        (d / (re.sub(r"[^a-z0-9]+", "_", page.lower()).strip("_")[:80] + ".html")).write_text(html)
    (d / "links.json").write_text(json.dumps(links, indent=1))
    for page, found in links.items():
        for url in found if isinstance(found, list) else []:
            if re.search(r"\.(xlsx?|csv)(\?|$)", url, re.I):
                name = urllib.parse.unquote(url.split("?")[0].rsplit("/", 1)[-1])
                try:
                    (d / name).write_bytes(get(url, tries=3))
                    print(f"  Forest 500: saved {name}", flush=True)
                except Exception as e:  # noqa: BLE001
                    print(f"  Forest 500: {url}: {e}", flush=True)


def main():
    OUT.mkdir(exist_ok=True)
    for step in (forest500, nport):
        try:
            step()
        except SystemExit as e:
            print(e, flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"  {step.__name__}: {e}", flush=True)


if __name__ == "__main__":
    main()
