"""
NASA Earthdata downloads for the tiles scripts (round 179b). The login is the
repository secrets EARTHDATA_USER and EARTHDATA_PASS (refresh.yml passes them
in). Files are found through NASA's Common Metadata Repository (CMR), which
needs no login; the download is redirected through urs.earthdata.nasa.gov,
which does, so the login is kept for that host only (NASA's own recipe).

Kept in scripts/lib/ so the refresh does not run it as a job of its own.
"""
import json, os, pathlib, time, urllib.parse

CMR = "https://cmr.earthdata.nasa.gov/search/"
URS = "urs.earthdata.nasa.gov"


def have_login():
    return bool(os.environ.get("EARTHDATA_USER") and os.environ.get("EARTHDATA_PASS"))


def session():
    import requests

    class S(requests.Session):
        def rebuild_auth(self, prepared, response):
            # Keep the login only on the way to and from NASA's login host.
            h = urllib.parse.urlparse(prepared.url).hostname
            if "Authorization" in prepared.headers and h != URS:
                o = urllib.parse.urlparse(response.request.url).hostname
                if o != h and o != URS:
                    del prepared.headers["Authorization"]

    s = S()
    s.auth = (os.environ["EARTHDATA_USER"], os.environ["EARTHDATA_PASS"])
    s.headers["User-Agent"] = "Culprits atlas build (github.com/WelcomeToYourGalaxy)"
    return s


def cmr(path, **params):
    import requests
    r = requests.get(CMR + path, params=params, timeout=120, headers={"Accept": "application/json"})
    r.raise_for_status()
    return r.json()


def collection(short_name=None, version=None, doi=None):
    p = {"page_size": 20}
    if doi:
        p["doi"] = doi
    if short_name:
        p["short_name"] = short_name
    if version:
        p["version"] = version
    entries = cmr("collections.json", **p)["feed"]["entry"]
    if not entries:
        raise RuntimeError(f"no NASA collection for {p}")
    # The cloud copy first where NASA keeps two.
    entries.sort(key=lambda e: (not str(e.get("data_center", "")).upper().endswith("CLOUD"), e.get("id", "")))
    return entries[0]


def granule_links(concept_id, temporal=None, suffix=None):
    """Every download link of a collection's files, oldest first."""
    out, page = [], 1
    while True:
        p = {"collection_concept_id": concept_id, "page_size": 2000, "page_num": page, "sort_key": "start_date"}
        if temporal:
            p["temporal"] = temporal
        ents = cmr("granules.json", **p)["feed"]["entry"]
        for g in ents:
            for l in g.get("links", []):
                h = l.get("href", "")
                if l.get("rel", "").endswith("/data#") and h.startswith("https") and (not suffix or h.lower().endswith(suffix)):
                    out.append({"href": h, "start": g.get("time_start"), "title": g.get("title")})
        if len(ents) < 2000:
            return out
        page += 1


def download(s, url, to, label):
    to = pathlib.Path(to)
    if to.exists() and to.stat().st_size > 0:
        return to
    for attempt in range(4):
        try:
            with s.get(url, stream=True, timeout=600) as r:
                r.raise_for_status()
                tmp = to.with_suffix(to.suffix + ".part")
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(1 << 20):
                        f.write(chunk)
                tmp.replace(to)
                return to
        except Exception as e:  # noqa: BLE001
            print(f"  {label}: {url.rsplit('/', 1)[-1]}: {e} (try {attempt + 1})", flush=True)
            time.sleep(10 * (attempt + 1))
    raise RuntimeError(f"could not download {url}")
