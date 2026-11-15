#!/usr/bin/env python3
"""
What is inside each file of the food-footprint package behind Halpern et al.
2022, "The environmental footprint of global food production" (KNB
doi:10.5063/F1V69H1B), listed into food/listing.txt so the soy and corn build
can be written from the real file names. Only each zip's table of contents is
read (by byte range) where KNB allows it; otherwise the zip is downloaded to
the runner and listed there, never kept. Nothing else is written.

By hand only (Actions tab, "food_list"); it does nothing on the daily run.
"""
import io, os, pathlib, struct, sys, tempfile, urllib.request, zipfile

OBJ = "https://knb.ecoinformatics.org/knb/d1/mn/v2/object/"
FILES = {
    "crops_food_feed_raw.zip": "urn:uuid:50cdc537-c52d-4b1c-8a51-2ba72fc36b27",
    "crops_food_raw.zip": "urn:uuid:2ada2da0-0b83-4982-bf6c-18054cb8db73",
    "crops_food_feed_rescaled.zip": "urn:uuid:7a0637a7-9c61-44be-9d2a-86ee9fb767e4",
    "global_food_pressures.zip": "urn:uuid:6e3860b2-21da-438e-91d6-64e213a1e721",
    "extra_production.zip": "urn:uuid:8cdb6f4f-8c06-495d-ab21-1096a2e5798b",
    "cumulative_rescaled_pressures.zip": "urn:uuid:3f49763d-f59e-43db-be86-2817659a0e83",
}
UA = {"User-Agent": "Culprits atlas (listing the food pressure package)"}


def url(pid):
    return OBJ + urllib.request.quote(pid, safe="")


def ranged(u, start, end):
    req = urllib.request.Request(u, headers=dict(UA, Range=f"bytes={start}-{end}"))
    with urllib.request.urlopen(req, timeout=300) as r:
        return r.status, r.read()


def names_by_range(u, size):
    st, tail = ranged(u, max(0, size - 65536), size - 1)
    if st != 206:
        return None
    at = tail.rfind(b"PK\x05\x06")
    if at < 0:
        return None
    cd_size, cd_off = struct.unpack("<II", tail[at + 12:at + 20])
    if cd_off == 0xFFFFFFFF:                         # zip64: fall back to the whole file
        return None
    st, cd = ranged(u, cd_off, cd_off + cd_size - 1)
    out, i = [], 0
    while i + 46 <= len(cd) and cd[i:i + 4] == b"PK\x01\x02":
        usize = struct.unpack("<I", cd[i + 24:i + 28])[0]
        n, e, c = struct.unpack("<HHH", cd[i + 28:i + 34])
        out.append((cd[i + 46:i + 46 + n].decode("utf-8", "replace"), usize))
        i += 46 + n + e + c
    return out


def size_of(u):
    req = urllib.request.Request(u, headers=UA, method="HEAD")
    with urllib.request.urlopen(req, timeout=120) as r:
        return int(r.headers.get("Content-Length") or 0)


def main():
    if os.environ.get("GITHUB_EVENT_NAME", "workflow_dispatch") != "workflow_dispatch":
        print("food_list: by hand only")
        return
    lines = []
    for name, pid in FILES.items():
        u = url(pid)
        try:
            size = size_of(u)
            got = names_by_range(u, size) if size else None
            how = "read by range"
            if got is None:
                how = "downloaded and listed"
                with tempfile.TemporaryFile() as tmp:
                    with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=1800) as r:
                        while True:
                            b = r.read(1 << 20)
                            if not b:
                                break
                            tmp.write(b)
                    tmp.seek(0)
                    got = [(i.filename, i.file_size) for i in zipfile.ZipFile(tmp).infolist()]
        except Exception as e:  # noqa: BLE001
            lines.append(f"\n=== {name} ===\n  could not be read: {e}")
            continue
        lines.append(f"\n=== {name} ({size / 1e6:.1f} MB, {how}; {len(got)} files) ===")
        lines += [f"  {n}  ({s / 1e6:.1f} MB)" for n, s in got]
        print(f"food_list: {name}: {len(got)} files ({how})", flush=True)
    out = pathlib.Path("food/listing.txt")
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"food_list: written {out}")


if __name__ == "__main__":
    main()
