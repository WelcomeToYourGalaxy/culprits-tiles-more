#!/usr/bin/env python3
"""
Forest 500's own downloads, the part of each row that describes the company or
financial institution (round 122b, asked 2 October 2026: "i downloaded all of
forest 500's data; add all").

Forest 500 (Global Canopy) gives its yearly masterfiles only through a form on
https://forest500.org/forest-500-data-methods/ ; the owner downloaded every
one (companies 2017 to 2025, financial institutions 2016 to 2025, and the
2022 country selection). Licence: Creative Commons Attribution-NonCommercial
4.0; cite "Forest 500 assessment data [Year], Global Canopy, Forest500.org".

Each masterfile row is one company or financial institution: first the columns
that describe it (name, subsidiaries, headquarters, website, sectors,
ownership, operating countries, the commodities it is a powerbroker for, its
scores), then its answer to every indicator. This keeps the first part, every
column of it as Forest 500 names it, for every row, and counts the answers.
The answers themselves stay in Forest 500's files.

Some years' files (companies 2018 to 2021) have broken quoting inside the
answers, so a row is cut into pieces partway; the describing columns come
first in the row and are read whole. A piece whose first cell is not the name
of a company Forest 500 assessed that year is not a row and is passed over;
how many were passed over is written down.

Reads forest500/download/ (the zips, as downloaded, zips inside zips too) and
forest500/rankings.json (every company and institution by year, from
Forest 500's API; scripts/defor_funds.py). Writes forest500/details.json:
{"CO" or "FI": {year: {name: {column: value}}}} and how each file was read.

By hand, when new downloads are added (FOREST500_DETAILS=1 in the refresh).
"""
import csv, io, json, os, pathlib, re, sys, zipfile

DOWNLOAD = pathlib.Path("forest500/download")
OUT = pathlib.Path("forest500/details.json")
csv.field_size_limit(1 << 30)


def walk(z, prefix=""):
    """Every csv in a zip, zips inside it opened too: (name, bytes)."""
    for n in z.namelist():
        if n.startswith("__MACOSX") or n.endswith("/"):
            continue
        b = z.read(n)
        if n.lower().endswith(".zip"):
            yield from walk(zipfile.ZipFile(io.BytesIO(b)), prefix + n + " > ")
        elif n.lower().endswith(".csv"):
            yield prefix + n, b


def clean(c):
    return re.sub(r'^[^A-Za-z0-9]+|"', "", c or "").strip()


def main(root="."):
    os.chdir(root)
    zips = sorted(DOWNLOAD.glob("*.zip"))
    if not zips:
        print("forest500_details: no downloads in forest500/download/; forest500/details.json kept as it is")
        return
    if OUT.exists() and not os.environ.get("FOREST500_DETAILS") and os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
        print("forest500_details: already read; FOREST500_DETAILS=1 reads the downloads again")
        return
    ranks = json.loads(pathlib.Path("forest500/rankings.json").read_text(encoding="utf-8"))["rows"]
    known = {}
    for r in ranks:
        known.setdefault((r["cotype"], r["ayear"]), set()).add(r["coname"].strip())
    out, read = {"CO": {}, "FI": {}}, []
    for zp in zips:
        for name, b in walk(zipfile.ZipFile(zp), zp.name + " > "):
            low = name.lower()
            if re.search(r"disclaimer|intro|methodology|overall approach|commodity data|old-format", low):
                continue
            kind = "FI" if re.search(r"financial|fis_", low) else "CO"
            # The year: the first year written in the innermost part of the
            # path that has one (a file's own name may also carry the date it
            # was published, after the year it covers).
            year = next((int(m.group()) for seg in reversed(name.split(" > ")) for m in [re.search(r"20[12]\d", seg)] if m), None)
            if year is None:
                read.append({"file": name, "skipped": "no year in its name"})
                continue
            rows = list(csv.reader(io.StringIO(b.decode("utf-8-sig", "replace"), newline="")))
            h = 2 if rows and rows[0] and rows[0][0].startswith("Commodity") else 0
            head = [clean(c) for c in rows[h]]
            namec = next((i for i, c in enumerate(head) if re.fullmatch(r"(company|fi name|entity name)", c, re.I)), None)
            if namec is None:
                read.append({"file": name, "skipped": "no name column"})
                continue
            cut = next((i for i, c in enumerate(head) if i > namec and (re.match(r"^\d+\.\d+", c) or c == "")), len(head))
            names = known.get((kind, year), set())
            got, passed = out[kind].setdefault(str(year), {}), 0
            for r in rows[h + 1:]:
                if len(r) <= namec or r[namec].strip() not in names or len(r) < cut:
                    if any(x.strip() for x in r):
                        passed += 1
                    continue
                rec = {head[i]: r[i].strip() for i in range(cut) if i != namec and r[i].strip() and r[i].strip() != "NA"}
                rec["_answers"] = sum(1 for x in r[cut:] if x.strip())
                got[r[namec].strip()] = rec
            read.append({"file": name, "kind": kind, "year": year, "columns": head[:cut], "rows": len(got),
                         "assessed that year (Forest 500's API)": len(names), "pieces passed over": passed})
    OUT.write_text(json.dumps({"licence": "CC BY-NC 4.0; Forest 500 assessment data [Year], Global Canopy, Forest500.org",
                               "read": read, **out}, ensure_ascii=False, separators=(",", ":")))
    for x in read:
        print("forest500_details:", json.dumps({k: v for k, v in x.items() if k != "columns"}, ensure_ascii=False))


if __name__ == "__main__":
    main(*sys.argv[1:])
