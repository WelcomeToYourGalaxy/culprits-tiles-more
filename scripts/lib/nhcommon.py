"""
Shared by the nonhuman_*.py scripts (the "Invasion of non-humans" map, maps
repo invasion-of-nonhumans.html, and the Culprits row that runs it). Everything
they make goes under nonhuman/ in this repo, a folder no other script writes.

Kept in scripts/lib/ so the refresh workflow does not run it as a job.
"""
import datetime, json, os, pathlib, re, shutil, subprocess, sys, time, unicodedata, urllib.request

OUT = pathlib.Path("nonhuman")
UA = {"User-Agent": "WelcomeToYourGalaxy Culprits map build (welcometoyourgalaxy@gmail.com)"}
BOUNDARIES = "https://raw.githubusercontent.com/WelcomeToYourGalaxy/culprits/main/map/data/boundaries.geojson"
RAMP10 = ["#E4F3F8", "#C6E7F0", "#9CD6E6", "#6FC2DA", "#46AACB", "#2E8FBA", "#2275A8", "#1A5C92", "#13447A", "#0C2E5E"]


def pip(*pkgs):
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", *pkgs], check=True)


def by_hand():
    return os.environ.get("GITHUB_EVENT_NAME", "workflow_dispatch") == "workflow_dispatch"


def stamp_path(name):
    return OUT / f"{name}.build.json"


def read_stamp(name):
    p = stamp_path(name)
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def write_stamp(name, data):
    OUT.mkdir(parents=True, exist_ok=True)
    data = dict(data, made=datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"))
    stamp_path(name).write_text(json.dumps(data, indent=1, ensure_ascii=False))


def due(name, every_days, env_flag, hand=True):
    """True when the script should build: run by hand (if hand), asked by its
    flag, never built, last build failed, or older than every_days (None =
    build once). Long builds pass hand=False, so running every script by hand
    does not start them again."""
    if os.environ.get(env_flag) or (hand and by_hand()):
        return True
    st = read_stamp(name)
    if not st or st.get("failed") or not st.get("made"):
        return True
    if every_days is None:
        print(f"{name}: built {st['made']}; a fixed release, so not built again (set {env_flag}=1 or run it by hand)")
        return False
    made = datetime.datetime.strptime(st["made"], "%Y-%m-%dT%H:%M:%SZ")
    if (datetime.datetime.utcnow() - made).days >= every_days:
        return True
    print(f"{name}: built {st['made']}; next build after {every_days} days")
    return False


def get(url, timeout=300, headers=None):
    req = urllib.request.Request(url, headers=dict(UA, **(headers or {})))
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def get_json(url, timeout=300, tries=4):
    last = None
    for i in range(tries):
        try:
            return json.loads(get(url, timeout))
        except Exception as e:
            last = e
            print(f"  {url}: {e}; try {i + 1} of {tries}", flush=True)
            time.sleep(5 * (i + 1))
    raise last


def download(url, path, label="", timeout=3600, session=None):
    path = pathlib.Path(path)
    if path.exists() and path.stat().st_size > 0:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    print(f"{label or path.name}: downloading {url}", flush=True)
    t0, got = time.time(), 0
    if session is not None:
        with session.get(url, stream=True, timeout=timeout) as r:
            r.raise_for_status()
            with open(tmp, "wb") as f:
                for b in r.iter_content(1 << 22):
                    f.write(b)
                    got += len(b)
    else:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=timeout) as r, open(tmp, "wb") as f:
            while True:
                b = r.read(1 << 22)
                if not b:
                    break
                f.write(b)
                got += len(b)
    os.replace(tmp, path)
    print(f"{label or path.name}: {got / 1e6:.1f} MB in {time.time() - t0:.0f} s", flush=True)
    return path


def write_json(rel, obj, compact=True):
    p = OUT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":") if compact else None, indent=None if compact else 1))
    return p


def slug(s, n=60):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    s = re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_").lower()
    return (s or "x")[:n]


def fold(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    s = s.replace("&", " and ")
    s = re.sub(r"\bthe\b", " ", s)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


# Names the sources write that neither the map's country list nor pycountry
# reads the same way. Only exact matches are taken: a name that matches nothing
# is listed as unplaced, never guessed.
ALIASES = {
    "usa": "USA", "us": "USA", "united states": "USA", "united states of america": "USA",
    "uk": "GBR", "united kingdom": "GBR", "great britain": "GBR", "united kingdom of great britain and northern ireland": "GBR",
    "russia": "RUS", "russian federation": "RUS", "south korea": "KOR", "republic of korea": "KOR", "korea republic of": "KOR", "korea south": "KOR",
    "north korea": "PRK", "democratic people s republic of korea": "PRK", "korea democratic people s republic of": "PRK",
    "iran": "IRN", "iran islamic republic of": "IRN", "syria": "SYR", "syrian arab republic": "SYR", "laos": "LAO",
    "lao people s democratic republic": "LAO", "vietnam": "VNM", "viet nam": "VNM", "bolivia": "BOL", "bolivia plurinational state of": "BOL",
    "venezuela": "VEN", "venezuela bolivarian republic of": "VEN", "tanzania": "TZA", "united republic of tanzania": "TZA",
    "tanzania united republic of": "TZA", "moldova": "MDA", "republic of moldova": "MDA", "czech republic": "CZE", "czechia": "CZE",
    "ivory coast": "CIV", "cote d ivoire": "CIV", "cote divoire": "CIV", "cape verde": "CPV", "cabo verde": "CPV",
    "swaziland": "SWZ", "eswatini": "SWZ", "macedonia": "MKD", "north macedonia": "MKD", "fyr macedonia": "MKD",
    "democratic republic of the congo": "COD", "democratic republic of congo": "COD", "dr congo": "COD", "congo dem rep": "COD",
    "congo democratic republic of the": "COD", "drc": "COD", "republic of the congo": "COG", "republic of congo": "COG", "congo": "COG",
    "congo rep": "COG", "brunei": "BRN", "brunei darussalam": "BRN", "taiwan": "TWN", "taiwan province of china": "TWN",
    "china taiwan province of": "TWN", "palestine": "PSE", "state of palestine": "PSE", "palestinian territories": "PSE",
    "turkey": "TUR", "turkiye": "TUR", "burma": "MMR", "myanmar": "MMR", "east timor": "TLS", "timor leste": "TLS",
    "micronesia": "FSM", "micronesia federated states of": "FSM", "federated states of micronesia": "FSM", "kosovo": "XKX",
    "gambia": "GMB", "the gambia": "GMB", "bahamas": "BHS", "the bahamas": "BHS", "netherlands": "NLD", "netherlands kingdom of the": "NLD",
    "china mainland": "CHN", "china": "CHN", "hong kong": "HKG", "china hong kong sar": "HKG", "macau": "MAC", "macao": "MAC",
    "china macao sar": "MAC", "saint kitts and nevis": "KNA", "st kitts and nevis": "KNA", "saint lucia": "LCA", "st lucia": "LCA",
    "saint vincent and the grenadines": "VCT", "st vincent and the grenadines": "VCT", "vatican": "VAT", "holy see": "VAT",
    "falkland islands": "FLK", "falkland islands malvinas": "FLK", "reunion": "REU", "curacao": "CUW", "sao tome and principe": "STP",
    "guinea bissau": "GNB", "equatorial guinea": "GNQ", "eq guinea": "GNQ", "bosnia and herzegovina": "BIH", "bosnia herzegovina": "BIH",
    "trinidad and tobago": "TTO", "antigua and barbuda": "ATG", "united arab emirates": "ARE", "uae": "ARE", "saudi arabia": "SAU",
    "south sudan": "SSD", "sudan": "SDN", "central african republic": "CAF", "dominican republic": "DOM", "new caledonia": "NCL",
    "french polynesia": "PYF", "french guiana": "GUF", "guadeloupe": "GLP", "martinique": "MTQ", "mayotte": "MYT", "greenland": "GRL",
    "puerto rico": "PRI", "guam": "GUM", "american samoa": "ASM", "northern mariana islands": "MNP", "us virgin islands": "VIR",
    "united states virgin islands": "VIR", "british virgin islands": "VGB", "cayman islands": "CYM", "turks and caicos islands": "TCA",
    "bermuda": "BMU", "faroe islands": "FRO", "faeroe islands": "FRO", "western sahara": "ESH", "somaliland": None,
}


class Countries:
    """Name and number lookups onto the iso3 codes of the map's own country
    shapes. Only codes that have a shape are returned; anything else is None."""

    def __init__(self):
        gj = get_json(BOUNDARIES)
        self.names = {}
        self.codes = set()
        for f in gj.get("features", []):
            p = f.get("properties") or {}
            if p.get("iso3"):
                self.codes.add(p["iso3"])
                self.names[fold(p.get("name"))] = p["iso3"]
        try:
            import pycountry  # noqa: F401
        except ImportError:
            pip("pycountry")
        import pycountry
        self.pc = pycountry

    def by_name(self, name):
        k = fold(name)
        if not k:
            return None
        if k in ALIASES:
            c = ALIASES[k]
            return c if c in self.codes else None
        if k in self.names:
            return self.names[k]
        for c in self.pc.countries:
            for attr in ("name", "official_name", "common_name"):
                if fold(getattr(c, attr, "")) == k:
                    return c.alpha_3 if c.alpha_3 in self.codes else None
        if len(k) == 3 and k.upper() in self.codes:
            return k.upper()
        if len(k) == 2:
            c = self.pc.countries.get(alpha_2=k.upper())
            if c and c.alpha_3 in self.codes:
                return c.alpha_3
        return None

    def by_m49(self, code):
        s = re.sub(r"\D", "", str(code or ""))
        if not s:
            return None
        c = self.pc.countries.get(numeric=s.zfill(3))
        return c.alpha_3 if c and c.alpha_3 in self.codes else None

    def by_alpha2(self, a2):
        c = self.pc.countries.get(alpha_2=str(a2 or "").upper())
        return c.alpha_3 if c and c.alpha_3 in self.codes else None


def tenths(values):
    """Ten classes cut at the deciles of the values given (positive, finite)."""
    import numpy as np
    v = np.asarray(values, dtype="float64")
    v = v[np.isfinite(v) & (v > 0)]
    if not v.size:
        return []
    qs = np.quantile(v, [i / 10 for i in range(1, 10)])
    return sorted(set(float(q) for q in qs if q > v.min()))


def sig(x):
    if x == 0:
        return "0"
    a = abs(x)
    if a >= 1000:
        return f"{x:,.0f}"
    if a >= 10:
        return f"{x:.1f}".rstrip("0").rstrip(".")
    if a >= 0.01:
        return f"{x:.3f}".rstrip("0").rstrip(".")
    return f"{x:.2e}"


def coded(grid, cuts):
    """A float grid as codes 1..len(cuts)+1 (0 = nothing: no data or 0)."""
    import numpy as np
    out = np.zeros(grid.shape, dtype=np.uint8)
    ok = np.isfinite(grid) & (grid > 0)
    out[ok] = (np.searchsorted(np.asarray(cuts), grid[ok], side="right") + 1).astype(np.uint8)
    return out


def ramp_key(cuts, lo, hi, unit=""):
    """[[colour, words]] for codes 1..n, and the palette {code: rgba}."""
    n = len(cuts) + 1
    cols = [RAMP10[round(i * (len(RAMP10) - 1) / max(1, n - 1))] for i in range(n)]
    edges = [lo] + list(cuts) + [hi]
    key, pal = [], {}
    for i in range(n):
        words = f"{sig(edges[i])} to {'under ' if i < n - 1 else ''}{sig(edges[i + 1])}{(' ' + unit) if unit else ''}"
        key.append([cols[i], words])
        h = cols[i]
        pal[i + 1] = (int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16), 235)
    return key, pal


def lib_pyramid():
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    import pyramid
    return pyramid


def tools():
    """ogr2ogr and tippecanoe, as mines.py installs them."""
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
    import mines
    mines.tools()
    return mines
