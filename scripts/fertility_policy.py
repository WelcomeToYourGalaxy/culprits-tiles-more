#!/usr/bin/env python3
"""
Governments' policies on how many children their people have: to raise the
birth rate, lower it, keep it as it is, or no policy (round 103b, asked 28
September, for Suppression > Sex).

Source: the United Nations Population Division's World Population Policies
(its inquiry of governments), the country data of its reproductive health
module (the 2021 revision; module III covers fertility), as the Division
publishes it for download. Each government's answer on its policy on the
fertility level is kept as the Division writes it, with every other column of
the country's row in the box.

The file's columns are found by their headings, not assumed: the build fails,
writing every sheet's headings to fertility/build.json, if no column about the
fertility level is found.

  fertility/policy.json   ISO3 -> {policy, year, x_<column>: value}
  fertility/build.json

Weekly (Mondays) or by hand.
"""
import datetime, io, json, os, pathlib, re, subprocess, sys, urllib.request

URLS = [
    "https://www.un.org/development/desa/pd/sites/www.un.org.development.desa.pd/files/desa_unpd_2021_13_inquiry_reproductive_health_country.xlsx",
]
OUT = pathlib.Path("fertility")
UA = {"User-Agent": "Mozilla/5.0 (Culprits atlas build; welcometoyourgalaxy@gmail.com)"}
NE = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_0_countries.geojson"


def get(url, timeout=300):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read()


def main():
    stamp = OUT / "build.json"
    if stamp.exists() and datetime.date.today().weekday() != 0 and os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
        print("fertility_policy: weekly; not Monday")
        return
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "openpyxl"], check=False)
    import openpyxl
    OUT.mkdir(exist_ok=True)
    seen, got = {}, None
    for url in URLS:
        try:
            wb = openpyxl.load_workbook(io.BytesIO(get(url)), read_only=True, data_only=True)
        except Exception as e:  # noqa: BLE001
            seen[url] = f"not read ({e})"
            continue
        for ws in wb.worksheets:
            rows = [[("" if c is None else str(c).strip()) for c in r] for r in ws.iter_rows(values_only=True)]
            # The heading row: the first of the top 15 with a country or ISO heading.
            hi = next((i for i, r in enumerate(rows[:15]) if any(re.search(r"^(country|iso|location|countries)", c, re.I) for c in r)), None)
            if hi is None:
                seen[f"{url} :: {ws.title}"] = [r for r in rows[:6]]
                continue
            head = rows[hi]
            seen[f"{url} :: {ws.title}"] = head
            fcol = next((j for j, h in enumerate(head) if re.search(r"fertility level|policy on fertility|level of fertility", h, re.I)), None)
            if fcol is None:
                continue
            got = (url, ws.title, head, rows[hi + 1:], fcol)
            break
        if got:
            break
    if not got:
        stamp.write_text(json.dumps({"found": False, "headings": seen, "date": datetime.date.today().isoformat()}, indent=1, ensure_ascii=False))
        raise SystemExit("fertility_policy: no column on the policy on the fertility level; headings in fertility/build.json")
    url, sheet, head, body, fcol = got
    iso_c = next((j for j, h in enumerate(head) if re.search(r"iso.?3|iso alpha|iso code|iso$", h, re.I)), None)
    name_c = next((j for j, h in enumerate(head) if re.search(r"^(country|location|countries)", h, re.I)), None)
    names = {}
    if iso_c is None:
        for f in json.loads(get(NE))["features"]:
            p = f["properties"]
            iso = p.get("ADM0_A3") if p.get("ISO_A3") in (None, "-99") else p["ISO_A3"]
            for k in ("NAME", "NAME_LONG", "ADMIN", "FORMAL_EN", "NAME_SORT"):
                if p.get(k):
                    names[str(p[k]).lower()] = iso
    out, unmatched, values = {}, [], {}
    for r in body:
        if len(r) <= fcol or not r[fcol]:
            continue
        iso = r[iso_c].upper() if iso_c is not None and len(r) > iso_c and re.fullmatch(r"[A-Za-z]{3}", r[iso_c] or "") else names.get((r[name_c] if name_c is not None else "").lower())
        if not iso:
            unmatched.append(r[name_c] if name_c is not None else r[:3])
            continue
        rec = {"policy": r[fcol], "name": r[name_c] if name_c is not None else iso}
        for j, h in enumerate(head):
            if h and j < len(r) and r[j] not in ("", None):
                rec[f"x_{h}"] = r[j]
        out[iso] = rec
        values[r[fcol]] = values.get(r[fcol], 0) + 1
    (OUT / "policy.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    stamp.write_text(json.dumps({"found": True, "url": url, "sheet": sheet, "column": head[fcol], "countries": len(out),
                                 "values": values, "not_matched": unmatched[:80], "headings": head,
                                 "date": datetime.date.today().isoformat()}, indent=1, ensure_ascii=False))
    print(f"fertility_policy: {len(out)} countries; {values}")


if __name__ == "__main__":
    main()
