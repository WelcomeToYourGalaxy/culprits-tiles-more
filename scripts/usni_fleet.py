#!/usr/bin/env python3
"""
The US Navy's ships at sea, week by week, as USNI News's Fleet and Marine
Tracker words it (round 79, 27 September). USNI publishes no coordinates:
each weekly article is a list of headings ("In the Philippine Sea", "In the
Arabian Sea") with paragraphs saying which carrier strike groups, amphibious
groups and ships are there. This copies the latest article and every one since
the copy began, a heading to a mark, the paragraphs quoted whole and linked.

A heading is drawn at the middle of the sea, ocean or port it names, from the
table below, and every box says so. A heading the table does not know is kept
in the file and listed, not placed.

Writes military/usni/<date>.geojson and military/usni/index.json.
"""
import html, json, pathlib, re, sys, urllib.request

OUT = pathlib.Path("military/usni")
UA = {"User-Agent": "Mozilla/5.0 (Culprits atlas daily copy; welcometoyourgalaxy@gmail.com)"}
FEEDS = ["https://news.usni.org/category/fleet-tracker/feed", "https://news.usni.org/feed"]
# The middle of each area, [lat, lon]. Approximate by nature: an area, not a position.
AREAS = {
    "philippine sea": [20, 130], "south china sea": [12, 114], "east china sea": [29, 125], "sea of japan": [40, 135],
    "western pacific": [15, 140], "eastern pacific": [10, -120], "pacific": [0, -160], "southern pacific": [-25, -120],
    "south pacific": [-25, -120], "north pacific": [40, -170], "indian ocean": [-10, 75], "arabian sea": [15, 63],
    "gulf of aden": [12.5, 48], "red sea": [20, 38.5], "persian gulf": [27, 51], "arabian gulf": [27, 51], "gulf of oman": [24.5, 58.5],
    "mediterranean": [35, 18], "mediterranean sea": [35, 18], "eastern mediterranean": [34, 30], "western mediterranean": [39, 5],
    "adriatic sea": [43, 15.5], "ionian sea": [38, 19], "black sea": [43, 34], "baltic sea": [58, 20], "north sea": [56, 3],
    "norwegian sea": [68, 3], "atlantic": [30, -40], "atlantic ocean": [30, -40], "north atlantic": [45, -35],
    "western atlantic": [32, -70], "eastern atlantic": [35, -20], "south atlantic": [-25, -15], "caribbean": [15, -75], "caribbean sea": [15, -75],
    "gulf of mexico": [25, -90], "coral sea": [-18, 155], "tasman sea": [-38, 160], "bering sea": [58, -178],
    "gulf of alaska": [57, -145], "arctic": [80, 0], "arctic ocean": [80, 0], "strait of hormuz": [26.6, 56.3], "taiwan strait": [24.5, 119.5],
    "yellow sea": [36, 123], "sea of okhotsk": [53, 150], "celebes sea": [3, 122], "sulu sea": [8, 120], "java sea": [-5, 111],
    "andaman sea": [11, 96], "bay of bengal": [15, 88], "gulf of guinea": [2, 4], "barents sea": [74, 40],
    "japan": [36, 138], "guam": [13.44, 144.79], "hawaii": [21.35, -157.95], "okinawa": [26.3, 127.8], "singapore": [1.3, 103.8],
    "bahrain": [26.2, 50.6], "djibouti": [11.55, 43.15], "spain": [36.62, -6.35], "greece": [35.49, 24.12], "australia": [-25, 134],
    "south korea": [36, 127.5], "korea": [36, 127.5], "philippines": [12, 122], "norway": [64, 11], "iceland": [65, -18],
}


def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read().decode("utf-8", "replace")


def text(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def latest():
    for f in FEEDS:
        try:
            rss = get(f)
        except Exception as e:  # noqa: BLE001
            print(f"  {f}: {e}", file=sys.stderr)
            continue
        for item in re.findall(r"<item>([\s\S]*?)</item>", rss):
            t = text((re.search(r"<title>([\s\S]*?)</title>", item) or [None, ""])[1].replace("<![CDATA[", "").replace("]]>", ""))
            if "fleet and marine tracker" in t.lower():
                link = text(re.search(r"<link>([\s\S]*?)</link>", item).group(1))
                date = (re.search(r"/(\d{4})/(\d\d)/(\d\d)/", link) or None)
                return t, link, "-".join(date.groups()) if date else ""
    raise RuntimeError("no Fleet and Marine Tracker article in the feeds")


def place(heading):
    h = heading.lower().replace("in the ", "").replace("in ", "", 1).strip(" .:")
    h = re.sub(r"^(the )", "", h)
    if h in AREAS:
        return AREAS[h]
    for k in sorted(AREAS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(k)}\b", h):
            return AREAS[k]
    return None


def main():
    title, link, date = latest()
    page = get(link)
    body = re.search(r'<div class="entry-content[^"]*">([\s\S]*?)</div>\s*<(?:footer|div class="(?:sharedaddy|entry-meta))', page)
    body = body.group(1) if body else page
    parts = re.split(r"<h[2-4][^>]*>([\s\S]*?)</h[2-4]>", body)
    lead = [text(p) for p in re.findall(r"<p[^>]*>([\s\S]*?)</p>", parts[0])]
    total = next((x for x in lead if re.search(r"battle force|deployed", x, re.I)), "")
    feats, unplaced = [], []
    for i in range(1, len(parts) - 1, 2):
        heading = text(parts[i])
        paras = [text(p) for p in re.findall(r"<p[^>]*>([\s\S]*?)</p>", parts[i + 1])]
        paras = [p for p in paras if p]
        if not heading or not paras:
            continue
        at = place(heading)
        if not at:
            unplaced.append(heading)
            continue
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [at[1], at[0]]},
                      "properties": {"name": heading, "said": "\n\n".join(paras), "week": date, "article": link, "title": title,
                                     "position": "the middle of the area USNI names; USNI gives no coordinates"}})
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{date}.geojson").write_text(json.dumps({"type": "FeatureCollection", "title": title, "article": link, "week": date,
                                                     "total": total, "unplaced": unplaced, "features": feats}, ensure_ascii=False, indent=1))
    weeks = sorted(p.stem for p in OUT.glob("*.geojson"))
    (OUT / "index.json").write_text(json.dumps({"weeks": weeks, "latest": weeks[-1] if weeks else None}, indent=1))
    print(f"usni_fleet: {title}: {len(feats)} areas placed" + (f"; not placed: {', '.join(unplaced)}" if unplaced else "") + f"; {len(weeks)} week(s) kept")


if __name__ == "__main__":
    main()
