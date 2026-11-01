#!/usr/bin/env python3
"""
A look inside the national environmental enforcement registers that answered
the probe of round 82b (round 100b): the probe saved only the first bytes of
each download. This opens each whole, and for every table inside writes its
columns, its row count and its first rows, so the registers can be mapped from
their real columns rather than from guesses.

  probe/enforcement/<name>_sample.json

Registers: Canada's Environmental Offenders Registry (every conviction under
Canada's federal environmental and wildlife acts), England's Environment
Agency enforcement actions, the US EPA's ECHO enforcement cases. By hand only.
"""
import csv, io, json, os, pathlib, zipfile, urllib.request

OUT = pathlib.Path("probe/enforcement")
UA = {"User-Agent": "Mozilla/5.0 (Culprits atlas build; welcometoyourgalaxy@gmail.com)"}
REGISTERS = {
    "canada_offenders_registry": "https://environmental-protection.canada.ca/offenders-registry/Home/Export",
    "england_ea_enforcement": "https://environment.data.gov.uk/public-register/downloads/enforcement-action",
    "us_epa_echo_cases": "https://echo.epa.gov/files/echodownloads/case_downloads.zip",
}


def tables(raw, name=""):
    if raw[:2] == b"PK":
        z = zipfile.ZipFile(io.BytesIO(raw))
        for n in z.namelist():
            if n.endswith("/"):
                continue
            yield from tables(z.read(n), n)
        return
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if name.lower().endswith((".csv", ".txt", "")) and "\n" in text[:200000]:
        first = text.split("\n", 1)[0]
        sep = max([",", ";", "\t", "|"], key=first.count)
        rows = list(csv.reader(io.StringIO(text), delimiter=sep))
        yield {"file": name, "separator": sep, "rows": len(rows) - 1, "columns": rows[0] if rows else [], "first_rows": rows[1:6]}
    else:
        yield {"file": name, "bytes": len(raw), "start": text[:400]}


def main():
    if os.environ.get("GITHUB_EVENT_NAME", "workflow_dispatch") != "workflow_dispatch":
        print("enforcement_sample: by hand only")
        return
    OUT.mkdir(parents=True, exist_ok=True)
    for name, url in REGISTERS.items():
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=900) as r:
                raw = r.read()
            got = list(tables(raw))
            print(f"{name}: {len(raw) / 1e6:.1f} MB, {len(got)} tables: " + "; ".join(f"{t['file']} ({t.get('rows', '?')} rows)" for t in got), flush=True)
        except Exception as e:  # noqa: BLE001
            got = [{"error": str(e)}]
            print(f"{name}: {e}", flush=True)
        (OUT / f"{name}_sample.json").write_text(json.dumps({"url": url, "tables": got}, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
