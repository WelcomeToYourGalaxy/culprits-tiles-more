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
The service hands out the 100 most recent alerts inside the area asked for, and
no more, whatever number is asked for (n=5000 returned 100 for every feed). Its
d= (days) is not applied either: asking for 30 days returned earthquakes from
2015. So this asks area by area: the whole world first, and wherever exactly
100 came back, that area's four quarters, and so on, with no limit on how far
down but the size of a building (MAX_DEPTH). An area that returns fewer than
100 has given everything it holds.

The one thing this cannot reach is more than 100 alerts at the very same spot
(spill reports are often pinned to a town's centre). Those spots are written to
feeds.json as "stacked", with how many were got. Only a date option on the
service would reach the rest, and none has been found yet.

SPREAD OVER DAYS
A busy feed needs thousands of requests for its whole history. Each run spends
at most MAX_REQUESTS per feed (set SKYTRUTH_REQUESTS to change it):
  1. what is new - from the world down, stopping at any full area whose 100
     alerts are all in the copy already, since nothing newer can be under it;
  2. then history - areas still waiting in feeds.json ("todo"), until the
     requests run out. What is left waits for tomorrow.
feeds.json says for each feed whether its history is complete.

NOTHING GATHERED IS LOST
Each run adds to the file already there (alerts are matched by SkyTruth's own
id for each), so an alert pushed out of the newest 100 tomorrow stays.

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
import html, json, os, pathlib, re, sys, time, urllib.request

API = "https://skytruth-alerts2.appspot.com/api"
OUT = pathlib.Path("skytruth")
CAP = 100               # what the service returns at most, for any area
MAX_DEPTH = 22          # the world quartered 22 times: a square about 5 m by 10 m
MAX_REQUESTS = int(os.environ.get("SKYTRUTH_REQUESTS") or 600)   # per feed per run, so one run cannot hammer their service
PAUSE = 0.2
SHARDS = 256
WORLD = [-85.0, -180.0, 85.0, 180.0, 0]

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
    req = urllib.request.Request(API + path, headers={"User-Agent": "Mozilla/5.0 (Culprits atlas daily copy)"})
    return json.loads(urllib.request.urlopen(req, timeout=120).read())


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


def harvest(feed, known=(), todo=None, fetch=get, pause=PAUSE, budget=None, walk_all=False):
    """One run's share of a feed. Returns (alerts by id, areas still to ask, stacked spots, requests made).

    known   ids already in the copy; a full area whose alerts are all known hides nothing newer
    todo    areas left over from earlier runs, still to be asked for history
    """
    budget = MAX_REQUESTS if budget is None else budget
    known = set(known)
    found, stacked, asked = {}, [], 0
    # With no list of areas left over, or when asked to, the walk stops nowhere
    # early: every full area is opened. main() asks for that on the 1st of each
    # month, in case an alert was added late under an old date, where the
    # "nothing newer under here" shortcut would not look.
    first = todo is None or walk_all
    fresh = [list(WORLD)]
    later = [list(t) for t in (todo or [])]

    def ask(sq):
        nonlocal asked
        s_, w, n, e = sq[:4]
        asked += 1
        rows = rows_of(fetch(f"/getalerts/?l={s_},{w},{n},{e}&d=30&selected={feed}&n=5000&keyword="))
        out = []
        for a in rows:
            a = unwrap(a)
            key = str(a.get("id") or json.dumps(a, sort_keys=True)[:200])
            found[key] = a
            out.append(key)
        if pause:
            time.sleep(pause)
        return out

    def quarters(sq, keys):
        s_, w, n, e, d = sq[:5]
        ms, mw = (s_ + n) / 2, (w + e) / 2
        # Each quarter carries what its parent returned (in memory only; a
        # quarter written to feeds.json for tomorrow drops it, harmlessly).
        return [[s_, w, ms, mw, d + 1, keys], [s_, mw, ms, e, d + 1, keys], [ms, w, n, mw, d + 1, keys], [ms, mw, n, e, d + 1, keys]]

    for queue, hunting_new in ((fresh, True), (later, False)):
        while queue and asked < budget:
            sq = queue.pop()
            try:
                keys = ask(sq)
            except Exception as ex:  # noqa: BLE001
                print(f"skytruth feed {feed}: area {sq[:4]}: {ex}", file=sys.stderr)
                later.append(sq) if hunting_new else queue.insert(0, sq)
                if not hunting_new:
                    break
                continue
            if len(keys) < CAP:
                continue                                  # this area has given everything it holds
            if sq[4] >= MAX_DEPTH:
                stacked.append({"at": sq[:4], "got": len(keys)})
                continue
            # The same 100 as the area's parent gave, all at one point: a stack
            # of alerts pinned to one spot. Quartering cannot separate them and
            # did not - two such spots cost 600 requests a run, every level of
            # quarters returning the same 100. The spot is recorded, and the
            # rest of the area is asked as the four strips round a metre-wide
            # box at that point: 4 requests instead of 22 levels of 4.
            spots = {(num(found[k].get("lat")), num(found[k].get("lng"))) for k in keys}
            parent_keys = sq[5] if len(sq) > 5 else None
            if len(spots) == 1 and parent_keys is not None and set(keys) == set(parent_keys):
                (lat, lng), = spots
                if lat is not None and lng is not None:
                    e_ = 1e-5
                    s_, w, n, e, d = sq[:5]
                    stacked.append({"at": [lat - e_, lng - e_, lat + e_, lng + e_], "got": len(keys)})
                    for strip in ([s_, w, lat - e_, e], [lat + e_, w, n, e], [lat - e_, w, lat + e_, lng - e_], [lat - e_, lng + e_, lat + e_, e]):
                        if strip[2] > strip[0] and strip[3] > strip[1]:
                            queue.append(strip + [d + 1])
                    continue
            if hunting_new and not first and all(k in known for k in keys):
                continue                                  # nothing newer under here; its history is already in todo or done
            queue.extend(quarters(sq, keys))
    left = [sq[:5] for sq in fresh + later]
    seen, todo_out = set(), []
    for sq in left:
        k = tuple(sq)
        if k not in seen:
            seen.add(k)
            todo_out.append(sq)
    return found, todo_out, stacked, asked


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
    for feed, label, name in [(10102, "vessels of concern", "vessels_of_concern")] + [(n, l, f"feed_{n}") for n, l in FEEDS.items()]:
        was = state.get(str(feed)) or {}
        store, old_file = OUT / name, OUT / f"{name}.geojson"
        before = load_all(store, old_file)
        known = set(before)
        # A feed gathered by the earlier script has no "todo": its history starts again from the world.
        waiting = was.get("todo") if "todo" in was else None
        if waiting == [] and was.get("history_paused_for_size"):
            waiting = [list(WORLD)]          # paused under the old size rule: its history starts again
        found, todo, stacked, asked = harvest(feed, known=known, todo=waiting, walk_all=time.gmtime().tm_mday == 1)
        if not found and not before:
            print(f"skytruth feed {feed} ({label}): nothing came back", file=sys.stderr)
            continue
        answered += 1
        kept = merged(store, old_file, features(found))
        save(store, kept, old_file)
        feats = list(kept.values())
        dates = sorted(str(f["properties"].get("incident_datetime") or "") for f in feats if f["properties"].get("incident_datetime"))
        nowhere = sum(1 for f in feats if not f.get("geometry"))
        spots = {json.dumps(x["at"]): x for x in (was.get("stacked") or []) + stacked}
        state[str(feed)] = {"what": label, "file": name, "alerts": len(feats), "new_today": len(set(found) - known),
                            "no_position": nowhere, "requests": asked, "oldest": dates[0] if dates else None,
                            "newest": dates[-1] if dates else None, "history_complete": not todo,
                            "todo": todo, "stacked": list(spots.values())}
        print(f"skytruth feed {feed} ({label}): {len(set(found) - known):,} new in {asked} requests; {len(feats):,} in the copy"
              f" ({nowhere:,} with no position), {dates[0] if dates else '?'} to {dates[-1] if dates else '?'}; "
              + ("history complete" if not todo else f"history not finished: {len(todo):,} areas wait for the next run")
              + (f"; {len(spots)} spots hold more than 100 alerts at one point and cannot be read past the newest 100" if spots else ""))
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
