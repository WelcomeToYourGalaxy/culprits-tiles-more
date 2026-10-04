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

Round 111b (29 September): the 2021 file read so far is the reproductive
health inquiry (laws on access to care: minimum ages, consent), which has no
question on the fertility level; its headings are in fertility/build.json.
The government's policy on the fertility level is in the Division's World
Population Policies 2019 country data on fertility, family planning and
reproductive health, which is now read first; the 2021 file stays as a last
try. The Division's sheets put their headings over two to four rows (a group
heading over its columns), so each column's heading is now the rows above the
data joined, the group heading carried across its columns. Countries are
matched by ISO code, by the UN's numeric country code, or by name.

Weekly (Mondays) or by hand.
"""
import datetime, io, json, os, pathlib, re, subprocess, sys, urllib.request

URLS = [
    "https://www.un.org/development/desa/pd/sites/www.un.org.development.desa.pd/files/desa_pd_2019_fertility_family_planning_reproductive_health_country_data.xlsx",
    "https://www.un.org/development/desa/pd/sites/www.un.org.development.desa.pd/files/desa_unpd_2021_13_inquiry_reproductive_health_country.xlsx",
]
OUT = pathlib.Path("fertility")
UA = {"User-Agent": "Mozilla/5.0 (Culprits atlas build; welcometoyourgalaxy@gmail.com)"}
NE = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_0_countries.geojson"


def get(url, timeout=300):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read()


def heads(rows, last, depth=4):
    """Each column's heading: the non-empty cells above the data, top to bottom,
    a group heading carried right across the empty cells after it."""
    top = max(0, last - depth + 1)
    width = max(len(r) for r in rows[top:last + 1])
    out = [[] for _ in range(width)]
    for i in range(top, last + 1):
        r = rows[i] + [""] * (width - len(rows[i]))
        carry = ""
        for j, c in enumerate(r):
            if i < last:
                carry = c or carry
                c = c or carry
            if c and (not out[j] or out[j][-1] != c):
                out[j].append(c)
    return [" | ".join(x) for x in out]


def data_row(r, head):
    """A row that names a country or code rather than a heading."""
    return any(re.fullmatch(r"[A-Z]{3}|\d{1,3}(\.0)?", c or "") for c in r[:6])


def main():
    stamp = OUT / "build.json"
    # Round 116b: a build that found nothing tries again the next day, not only on Mondays.
    try:
        found = json.loads(stamp.read_text()).get("found") if stamp.exists() else None
    except Exception:  # noqa: BLE001
        found = None
    if found and datetime.date.today().weekday() != 0 and os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
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
            # The heading row: the first of the top 20 with a country or ISO heading.
            hi = next((i for i, r in enumerate(rows[:20]) if any(re.search(r"^(country|iso|location|countries|region, subregion or country)", c, re.I) for c in r)), None)
            if hi is None:
                seen[f"{url} :: {ws.title}"] = [r for r in rows[:6]]
                continue
            head = heads(rows, hi)
            first = next((i for i in range(hi + 1, min(hi + 8, len(rows))) if any(c for c in rows[i]) and data_row(rows[i], head)), hi + 1)
            head = heads(rows, first - 1)
            seen[f"{url} :: {ws.title}"] = head
            pat = r"fertility level|policy on fertility|level of fertility|policy.{0,40}fertility"
            fcol = next((j for j, h in enumerate(head) if re.search(pat, h.split(" | ")[-1], re.I)), None)
            if fcol is None:
                fcol = next((j for j, h in enumerate(head) if re.search(r"fertility level|policy on fertility|level of fertility", h, re.I)), None)
            if fcol is None:
                continue
            got = (url, ws.title, head, rows[first:], fcol)
            break
        if got:
            break
    if not got:
        stamp.write_text(json.dumps({"found": False, "headings": seen, "date": datetime.date.today().isoformat()}, indent=1, ensure_ascii=False))
        raise SystemExit("fertility_policy: no column on the policy on the fertility level; headings in fertility/build.json")
    url, sheet, head, body, fcol = got
    iso_c = next((j for j, h in enumerate(head) if re.search(r"iso.?3|iso alpha|iso code|iso$", h, re.I)), None)
    code_c = next((j for j, h in enumerate(head) if re.search(r"country code|location code|m49|loc ?id", h, re.I)), None)
    name_c = next((j for j, h in enumerate(head) if re.search(r"(^|\| )(country|location|countries|region, subregion or country)", h, re.I)), None)
    names, numeric = {}, {}
    for f in json.loads(get(NE))["features"]:
        p = f["properties"]
        iso = p.get("ADM0_A3") if p.get("ISO_A3") in (None, "-99") else p["ISO_A3"]
        for k in ("NAME", "NAME_LONG", "ADMIN", "FORMAL_EN", "NAME_SORT"):
            if p.get(k):
                names[str(p[k]).lower()] = iso
        if str(p.get("ISO_N3") or "").lstrip("0").isdigit():
            numeric[int(p["ISO_N3"])] = iso
    out, unmatched, values = {}, [], {}
    for r in body:
        if len(r) <= fcol or not r[fcol]:
            continue
        iso = r[iso_c].upper() if iso_c is not None and len(r) > iso_c and re.fullmatch(r"[A-Za-z]{3}", r[iso_c] or "") else None
        if not iso and code_c is not None and len(r) > code_c and re.fullmatch(r"\d{1,3}(\.0)?", r[code_c] or ""):
            iso = numeric.get(int(float(r[code_c])))
        if not iso and name_c is not None and len(r) > name_c:
            nm = re.sub(r"\s*[*\d]+$", "", r[name_c] or "").strip().lower()
            iso = names.get(nm)
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
