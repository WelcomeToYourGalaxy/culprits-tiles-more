#!/usr/bin/env python3
"""
SkyTruth Monitor's alert feeds, copied daily into skytruth/, since its service
is built for its own page and cannot be read by another website.

  skytruth/vessels_of_concern.geojson   the "Vessels of concern" public map (its feed, 10102)
  skytruth/issue.json                   that map's own description
  skytruth/feed_<n>.geojson             one file per alert feed (FEEDS below)
  skytruth/feeds.json                   for each feed: how many alerts the copy holds, the
                                        oldest and newest, and any squares that were still full

NOTHING IS LEFT OUT
The owner asked (20 September 2026) that nothing SkyTruth publishes be excluded.

  Every feed.      All ten that answered when feed numbers 1 to 30 and 10095 to
                   10110 were asked: the nine in FEEDS, the developers' test
                   entries (10101) and Vessels of concern (10102).
  Every alert.     See below: the back history is fetched too, over several days.
  No position.     An alert with no position cannot be drawn, but it is kept in
                   the file (with no geometry) and counted, and the map's row
                   says how many there are.
  Its own text.    Kept whole in "content". The box shown on the map (_html) is
                   the same text with its images, made safe: see clean_html.

HOW EVERY ALERT IS REACHED
SkyTruth answered our questions by email on how to read the service:

  overridenum   raises the 100-alert limit. They ask for no more than 20,000.
  startdate,    a date range, as YYYY-MM-DD. It is the date the incident
  enddate       happened, not when it was published. Incidents are published
                about two weeks after they happen, on average.
  no paging     there is no "next page", and no bulk download.
  utm_origin    every request carries utm_origin=welcome_to_your_galaxy, as asked.
  pace          under about 2 requests a second, for no longer than 30 minutes,
                at night in the Western Hemisphere. refresh.yml runs at 06:17 UTC.

So a feed is read by date. The whole feed is asked for first; if 20,000 come
back there may be more, so it is asked for year by year, and any period that
still returns 20,000 is cut in half until it fits. This replaces the earlier
walk over smaller and smaller map squares, which could not get past 100 alerts
pinned to one spot. Only more than 20,000 alerts on a single day could stop it;
such a day would be written to feeds.json as "stacked".

EACH RUN
  1. what is new - the last RECENT_DAYS days, long enough for late publishing;
  2. then history - periods still waiting in feeds.json ("todo"), until this
     feed's share of the run's time runs out. What is left waits for tomorrow.
On the 1st of each month every feed is read again in full, in case an alert was
added late under an old date. Small feeds go first, so the busy ones take
whatever time is left. feeds.json says for each feed whether its history is
complete. A feed last read by the old map-square walk ("walk" missing from
feeds.json) starts its history again, which also recovers what the 100-at-one-
spot limit lost.

NOTHING GATHERED IS LOST
Each run adds to the file already there (alerts are matched by SkyTruth's own
id for each), so an alert the service stops returning stays in the copy.

SIZE, AND HOW THE COPY IS KEPT
GitHub refuses a file over 100 MB, and after two runs the violations feed alone
was 86 MB in one file. So a feed's copy is kept in 256 pieces:
skytruth/feed_<n>/<hh>.json, each a {id: feature} map, an alert filed by the
shard() of its id (FNV-1a hash, two hex digits). The map's box for an alert
reads only the piece that alert is in (map/app.js computes the same shard),
and scripts/skytruth_tiles.py builds each feed's tiles from the pieces. A feed
still in the old single file (feed_<n>.geojson) is moved into pieces on the
first run and the old file removed. Nothing is paused for size any more.
"""
import datetime, html, json, os, pathlib, re, sys, time, urllib.request

API = "https://skytruth-alerts2.appspot.com/api"
OUT = pathlib.Path("skytruth")
CAP = 20000             # the most SkyTruth asks us to request at once (overridenum)
ORIGIN = "welcome_to_your_galaxy"   # how SkyTruth asked this script to identify itself
MAX_REQUESTS = int(os.environ.get("SKYTRUTH_REQUESTS") or 600)   # per feed per run
PAUSE = 0.6             # with each request's own time, well under their 2 a second
RUN_SECONDS = int(os.environ.get("SKYTRUTH_SECONDS") or 25 * 60)  # they asked for no longer than 30 minutes
RECENT_DAYS = 60
FIRST_YEAR = 1970       # before this, one period: the oldest alert held is from 1982
SHARDS = 256
WALK = 2                # 2: read by date. Missing: the old map-square walk
WORLD = "-85,-180,85,180"

FEEDS = {
    1: "US National Response Center incident reports",
    2: "incidents written up by SkyTruth",
    3: "US marine incident reports",
    4: "Pennsylvania oil and gas drilling permits",
    5: "Pennsylvania drilling starts (SPUD)",
    6: "earthquakes",
    8: "well permit activity",
    9: "Pennsylvania permit violations",
    10: "FracFocus fracking disclosures",
    10101: "test entries left by SkyTruth Monitor's developers",
}


def get(path):
    path += ("&" if "?" in path else "?") + f"utm_origin={ORIGIN}"
    req = urllib.request.Request(API + path, headers={"User-Agent": "Mozilla/5.0 (Culprits atlas daily copy)"})
    return json.loads(urllib.request.urlopen(req, timeout=300).read())


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def point(a):
    for la, lo in (("lat", "lng"), ("lat", "lon"), ("latitude", "longitude")):
        if num(a.get(la)) is not None and num(a.get(lo)) is not None:
            return [num(a[lo]), num(a[la])]
    g = a.get("geometry") or a.get("location")
    if isinstance(g, dict) and g.get("coordinates"):
        return g["coordinates"][:2]
    if isinstance(g, str):
        m = [num(x) for x in g.replace("POINT", "").strip("() ").split()]
        if len(m) == 2 and None not in m:
            return m
    return None


def unwrap(o):
    """Django's serialised shape: {"model": ..., "pk": ..., "fields": {...}}."""
    if isinstance(o, dict) and isinstance(o.get("fields"), dict):
        out = dict(o["fields"])
        out.setdefault("id", o.get("pk"))
        return out
    return o


# An alert's own text is HTML written by SkyTruth, by agencies, and (feed 10101
# shows) by anyone with an account. It is shown in a box on the map, so it is
# cut down to plain formatting, links and pictures before it is shown: no
# scripts, no frames, no attributes but a link's href and a picture's src, and
# both only if they are ordinary web addresses. One thing is not a picture and is
# left out of the box: SkyTruth's ga.php, an invisible 1-pixel counter that
# reports each reader to their analytics. The untouched text stays in "content".
KEEP = {"img", "b", "strong", "i", "em", "u", "br", "p", "div", "span", "ul", "ol", "li", "table", "tr", "td", "th", "tbody", "thead", "h3", "h4", "h5", "a"}


def clean_html(text):
    text = re.sub(r"(?is)<(script|style|iframe|object|embed|svg|form)\b.*?</\1\s*>", "", str(text or ""))
    text = re.sub(r"(?is)<!--.*?-->", "", text)

    def tag(m):
        close, name, attrs = m.group(1), m.group(2).lower(), m.group(3) or ""
        if name not in KEEP:
            return ""
        if close:
            return f"</{name}>"
        if name == "img":
            got = re.search(r"""src\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""", attrs, re.I)
            url = html.unescape((got.group(1) or got.group(2) or got.group(3) or "").strip()) if got else ""
            if url.startswith("../"):
                url = "https://monitor.skytruth.org/" + url.lstrip("./")
            if not re.match(r"https?://", url, re.I) or re.search(r"/ga\.php", url, re.I):
                return ""
            return f'<img src="{html.escape(url, quote=True)}" style="max-width:100%;height:auto" loading="lazy" referrerpolicy="no-referrer" alt="">'
        if name == "a":
            href = re.search(r"""href\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""", attrs, re.I)
            url = html.unescape((href.group(1) or href.group(2) or href.group(3) or "").strip()) if href else ""
            if re.match(r"https?://", url, re.I):
                return f'<a href="{html.escape(url, quote=True)}" target="_blank" rel="noopener noreferrer">'
            return "<a>"
        return f"<{name}>"
    return re.sub(r"(?s)<\s*(/?)\s*([a-zA-Z][a-zA-Z0-9]*)\b([^>]*)>", tag, text).strip()


def box(props):
    """The alert as SkyTruth words it, made safe: its title, its date, its own text."""
    parts = [f"<h4 style=\"margin:0 0 6px\">{html.escape(str(props.get('title') or 'Alert'))}</h4>"]
    if props.get("incident_datetime"):
        parts.append(f"<div class=\"meta\">{html.escape(str(props['incident_datetime']))}</div>")
    body = clean_html(props.get("content")) or clean_html(props.get("summary"))
    if body:
        parts.append(f"<div>{body}</div>")
    return "".join(parts)


def rows_of(got):
    return got if isinstance(got, list) else (got.get("alerts") or got.get("results") or got.get("features") or [])


def years(today):
    """The whole of time as periods to ask: everything before FIRST_YEAR, each year, and anything dated ahead."""
    out = [["1900-01-01", f"{FIRST_YEAR - 1}-12-31"]]
    out += [[f"{y}-01-01", f"{y}-12-31"] for y in range(FIRST_YEAR, today.year)]
    out += [[f"{today.year}-01-01", f"{today.year + 1}-12-31"]]
    return out


def halves(period):
    a, z = (datetime.date.fromisoformat(d) for d in period)
    mid = a + (z - a) // 2
    return [[a.isoformat(), mid.isoformat()], [(mid + datetime.timedelta(days=1)).isoformat(), z.isoformat()]]


def harvest(feed, todo=None, full=False, fetch=get, pause=PAUSE, budget=None, deadline=None, today=None):
    """One run's share of a feed. Returns (alerts by id, periods still to ask, full single days, requests made).

    todo    periods left over from earlier runs, still to be asked for history
    full    read everything again: the whole feed first, then by year if it was too big
    """
    budget = MAX_REQUESTS if budget is None else budget
    today = today or datetime.date.today()
    found, stacked, asked = {}, [], 0

    def ask(period=None):
        nonlocal asked
        when = f"&startdate={period[0]}&enddate={period[1]}" if period else ""
        asked += 1
        rows = rows_of(fetch(f"/getalerts/?l={WORLD}&d=30&selected={feed}&n=5000&keyword=&overridenum={CAP}{when}"))
        for a in rows:
            a = unwrap(a)
            found[str(a.get("id") or json.dumps(a, sort_keys=True)[:200])] = a
        if pause:
            time.sleep(pause)
        return len(rows)

    def time_left():
        return asked < budget and (deadline is None or time.monotonic() < deadline)

    later = [list(t) for t in (todo or [])]
    if full:
        try:
            later = [] if ask() < CAP else years(today)
        except Exception as ex:  # noqa: BLE001
            print(f"skytruth feed {feed}: the whole feed: {ex}", file=sys.stderr)
            later = years(today)
    else:
        # What is new, and first, whatever the state of the history.
        recent = [(today - datetime.timedelta(days=RECENT_DAYS)).isoformat(), (today + datetime.timedelta(days=1)).isoformat()]
        later.insert(0, recent)
    failures = 0
    while later and time_left() and failures < 3:
        period = later.pop(0)
        try:
            got = ask(period)
            failures = 0
        except Exception as ex:  # noqa: BLE001
            print(f"skytruth feed {feed}: {period[0]} to {period[1]}: {ex}", file=sys.stderr)
            later.append(period)
            failures += 1
            continue
        if got < CAP:
            continue                                  # this period has given everything it holds
        if period[0] == period[1]:
            stacked.append({"day": period[0], "got": got})
            continue
        later[:0] = halves(period)
    return found, later, stacked, asked


def features(found):
    feats = []
    for key, a in found.items():
        props = a.get("properties", a) if isinstance(a, dict) else {}
        at = point(a) or point(props)
        clean = {k: v for k, v in props.items() if isinstance(v, (str, int, float, bool)) and k not in ("lat", "lng", "lon")}
        clean["id"] = key
        clean["_html"] = box(props)
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": at} if at else None, "properties": clean})
    return feats


def shard(key):
    """Which of the 256 pieces an alert is in: FNV-1a over its id, as two hex digits.
    map/app.js has the same function; the two must agree."""
    h = 0x811C9DC5
    for b in str(key).encode("utf-8"):
        h = ((h ^ b) * 0x01000193) & 0xFFFFFFFF
    return f"{h % SHARDS:02x}"


def load_all(store, old_file=None):
    """Every alert kept for a feed: the pieces, plus the old single file if it is still there."""
    kept = {}
    if old_file and old_file.exists():
        try:
            for f in json.loads(old_file.read_text(encoding="utf-8")).get("features", []):
                kept[str(f["properties"].get("id"))] = f
        except Exception as ex:  # noqa: BLE001
            print(f"skytruth: {old_file} could not be read ({ex})", file=sys.stderr)
    if store.exists():
        for piece in sorted(store.glob("*.json")):
            try:
                kept.update(json.loads(piece.read_text(encoding="utf-8")))
            except Exception as ex:  # noqa: BLE001
                print(f"skytruth: {piece} could not be read ({ex})", file=sys.stderr)
    return kept


def merged(store, old_file, fresh):
    """What was gathered before, with today's on top: nothing already kept is dropped."""
    kept = load_all(store, old_file)
    for f in fresh:
        kept[str(f["properties"]["id"])] = f
    return kept


def save(store, kept, old_file=None):
    """Write the pieces, only those that changed, then retire the old single file."""
    store.mkdir(parents=True, exist_ok=True)
    by = {}
    for key, f in kept.items():
        by.setdefault(shard(key), {})[key] = f
    for hh in sorted(by):
        text = json.dumps(dict(sorted(by[hh].items())), ensure_ascii=False, separators=(",", ":"))
        piece = store / f"{hh}.json"
        if not piece.exists() or piece.read_text(encoding="utf-8") != text:
            piece.write_text(text, encoding="utf-8")
    if old_file and old_file.exists():
        old_file.unlink()


def main():
    OUT.mkdir(exist_ok=True)
    state_path = OUT / "feeds.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    except Exception:  # noqa: BLE001
        state = {}
    try:
        issue = get("/getissue/?id=vessels-of-concern")
        (OUT / "issue.json").write_text(json.dumps(issue, ensure_ascii=False), encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        print(f"skytruth: the vessels-of-concern map's description could not be read ({e})", file=sys.stderr)
    answered = 0
    jobs = [(10102, "vessels of concern", "vessels_of_concern")] + [(n, l, f"feed_{n}") for n, l in FEEDS.items()]
    jobs.sort(key=lambda j: (state.get(str(j[0])) or {}).get("alerts") or 0)   # small feeds first; the busy ones take what is left
    end = time.monotonic() + RUN_SECONDS
    for at, (feed, label, name) in enumerate(jobs):
        was = state.get(str(feed)) or {}
        store, old_file = OUT / name, OUT / f"{name}.geojson"
        before = load_all(store, old_file)
        known = set(before)
        now = time.monotonic()
        share = now + max(0, end - now) / (len(jobs) - at)
        moved = was.get("walk") != WALK      # last read by the old map-square walk: its "todo" and "stacked" no longer apply
        if moved:
            was = {k: v for k, v in was.items() if k not in ("todo", "stacked")}
        monthly = time.gmtime().tm_mday == 1 and not was.get("todo")
        found, todo, stacked, asked = harvest(feed, todo=was.get("todo"), full=moved or monthly, deadline=share)
        if not found and not before:
            print(f"skytruth feed {feed} ({label}): nothing came back", file=sys.stderr)
            continue
        answered += 1
        kept = merged(store, old_file, features(found))
        save(store, kept, old_file)
        feats = list(kept.values())
        dates = sorted(str(f["properties"].get("incident_datetime") or "") for f in feats if f["properties"].get("incident_datetime"))
        nowhere = sum(1 for f in feats if not f.get("geometry"))
        spots = {x["day"]: x for x in (was.get("stacked") or []) + stacked}
        state[str(feed)] = {"what": label, "file": name, "alerts": len(feats), "new_today": len(set(found) - known),
                            "no_position": nowhere, "requests": asked, "oldest": dates[0] if dates else None,
                            "newest": dates[-1] if dates else None, "history_complete": not todo,
                            "todo": todo, "stacked": list(spots.values()), "walk": WALK}
        print(f"skytruth feed {feed} ({label}): {len(set(found) - known):,} new in {asked} requests; {len(feats):,} in the copy"
              f" ({nowhere:,} with no position), {dates[0] if dates else '?'} to {dates[-1] if dates else '?'}; "
              + ("history complete" if not todo else f"history not finished: {len(todo):,} periods wait for the next run")
              + (f"; {len(spots)} single days hold {CAP:,} alerts or more and cannot be read in full" if spots else ""))
    if not answered:
        sys.exit("skytruth: no feed answered; the last good copies stay")
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    # The tiles, from the pieces just written. Done here rather than as its own
    # job because the workflow runs every script at the same time: run apart,
    # skytruth_tiles found no pieces yet and built nothing.
    try:
        import skytruth_tiles
        skytruth_tiles.main()
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        print(f"skytruth: the tiles could not be built ({e}); the copy is saved all the same", file=sys.stderr)


if __name__ == "__main__":
    main()
