#!/usr/bin/env python3
"""
Planted, bought or captured (round 109b, asked 28 September): lawmakers,
judges, rulers, officials and company heads found working for, paid by, or
tied to someone other than the people they answer to, worldwide, as far back
as the records go. The owner asked for every tier of proof, each marked.

Two sources, merged into one file:

  1. Wikidata (CC0), read each week. Three questions:
     a. People who held any office Wikidata records (P39) and who worked for,
        belonged to or were affiliated with (P108, P463, P1416) a spy service
        or secret police, or whose occupation (P106) is spy, intelligence
        officer or agent, informant and the like. The kinds of service and
        occupation are found each week by their English names (printed in
        the log), with every narrower kind below them.
     b. People who held any office and were convicted (P1399) of a crime
        whose English name speaks of spying, treason, bribery, foreign
        agency or state secrets (the crimes found are printed in the log).
     c. People convicted of such a crime, holding no office, whose employer
        (P108) is a business: company heads and staff convicted of bribery,
        and spies convicted of stealing from companies.
     Each person is placed where their office's jurisdiction (P1001) is (its
     own coordinates, or its capital's), else their office's country's
     capital, else their employer's head office, else their citizenship's
     capital. The branch (lawmaking, courts, ruling and running, company, other
     office) is read from the office's English name; the words are in BRANCH.
  2. CASES below: cases compiled for this map on 28 September 2026 from the
     sources in each box, including ties and allegations, each marked; with
     named Colombian members of Congress convicted for parapolitics (round
     109d) and Andrej Babiš's StB records.
  3. Lists read each week (round 109d): Wikipedia's List of Americans in the
     Venona papers and the Mitrokhin Archive article (people named, each
     placed at their country's capital through Wikidata), Spanish Wikipedia's
     parapolitics article (its lists of members of Congress), and every case
     on the SEC's page of FCPA enforcement actions, one point for each country
     the SEC says bribes or improper payments went to.
  4. Round 110c: every Wikipedia's category of people registered by the
     secret police (Czech, Slovak, Polish, German, Romanian, Bulgarian), each
     placed through Wikidata; and Poland's IPN catalogue of people in public
     office, read a slice a day by scripts/capture_ipn.py (capture/ipn.geojson).
     Probes: the Czech Security Services Archive and Slovakia's Nation's Memory
     Institute registers, and one IPN entry, are saved to probe/capture/ for a
     later round. Also every case on the US Justice Department's yearly lists of
     FCPA and related enforcement actions (1977 on), placed at the court
     district's city.
     If a part gives nothing one week, last week's copy of it is kept.

  capture/cases.geojson   group = what proves it (TIERS); branch; captor
  capture/build.json      counts, the kinds and crimes found, any errors

Weekly (Mondays), or by hand.
"""
import datetime, json, os, pathlib, re, sys, time, urllib.parse, urllib.request

OUT = pathlib.Path("capture")
UA = {"User-Agent": "Culprits atlas build (https://github.com/WelcomeToYourGalaxy/culprits-tiles-more; welcometoyourgalaxy@gmail.com)",
      "Accept": "application/sparql-results+json"}
SPARQL = "https://query.wikidata.org/sparql"

TIERS = {
    "court": "Convicted, or found by a court",
    "inquiry": "Found by an official inquiry",
    "archive": "Named in opened secret-police or spy-service files",
    "admitted": "Admitted by the person, or by the side that paid or ran them",
    "served": "Held office and worked for a spy service or secret police (Wikidata)",
    "ties": "Documented ties, funding, or laws written for them",
    "settled": "Settled bribery charges with a regulator (often without admitting or denying)",
    "alleged": "Charged or alleged, not proven",
}

AGENCY_NAMES = ["intelligence agency", "secret police", "security agency", "counterintelligence agency",
                "signals intelligence agency", "military intelligence", "state security agency", "espionage agency"]
OCCUPATION_NAMES = ["spy", "intelligence officer", "intelligence agent", "secret agent", "double agent", "informant",
                    "unofficial collaborator", "mole", "sleeper agent", "agent of influence"]
BUSINESS_NAMES = ["business", "enterprise", "company"]
CRIME_WORDS = r"espionage|spy|treason|brib|kickback|foreign agent|agent of a foreign|state secret|collusion|influence peddling|trade secret|corrupt practices"

BRANCH = [
    ("courts", r"judge|justice|court|magistrate|prosecutor|attorney general|procurator|tribunal"),
    ("lawmaking", r"member of (the )?(parliament|congress|house|senate|assembly|bundestag|volkskammer|reichstag|duma|diet|legislat|chamber|cortes|sejm|seimas|saeima|riigikogu|knesset|lok sabha|rajya sabha|national council|federal council|landtag|state duma|supreme soviet|people's congress)|senator|deputy|legislator|representative|councillor|councilor|member of .*council|mep\b|assemblyman|assemblywoman|alderman|speaker of"),
    ("ruling and running", r"president|prime minister|chancellor|premier|king|queen|monarch|emperor|sultan|emir|head of state|head of government|minister|secretary of|secretary-general|secretary general|governor|mayor|ambassador|director|chief of|commissioner|chairman of the council|dictator|leader of|first secretary|general secretary|cabinet|state secretary|under secretary|undersecretary|commander"),
    ("company", r"chief executive|ceo|chairman|chairperson|board member|member of the board|company director|managing director|executive"),
]


def branch_of(names):
    for key, rx in BRANCH:
        if any(re.search(rx, n or "", re.I) for n in names):
            return key
    return "other office"


def sparql(q, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(SPARQL, data=urllib.parse.urlencode({"query": q, "format": "json"}).encode(), headers=UA)
            with urllib.request.urlopen(req, timeout=320) as r:
                return json.loads(r.read())["results"]["bindings"]
        except Exception as e:  # noqa: BLE001
            last = e
            print(f"  query failed ({type(e).__name__}: {e}); try {i + 1} of {tries}", flush=True)
            time.sleep(20 * (i + 1))
    raise last


def v(b, k):
    return b.get(k, {}).get("value", "")


def qid(url):
    return url.rsplit("/", 1)[-1]


def classes(names, found):
    """Items named exactly so in English (not disambiguation pages), with every narrower kind below them."""
    vals = " ".join(json.dumps(n) + "@en" for n in names)
    rows = sparql(f"""SELECT DISTINCT ?c ?cLabel WHERE {{
      VALUES ?l {{ {vals} }} ?base rdfs:label ?l.
      FILTER NOT EXISTS {{ ?base wdt:P31 wd:Q4167410 }}
      ?c wdt:P279* ?base.
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }} }}""")
    out = sorted({qid(v(b, "c")) for b in rows})
    found[", ".join(names)] = sorted({f"{qid(v(b, 'c'))} {v(b, 'cLabel')}" for b in rows})[:400]
    print(f"  {len(out)} kinds for {names}", flush=True)
    return out


PLACE = """
      OPTIONAL { ?pos wdt:P1001 ?jur. OPTIONAL { ?jur wdt:P625 ?c1 } OPTIONAL { ?jur wdt:P36/wdt:P625 ?c2 } }
      OPTIONAL { ?pos wdt:P17/wdt:P36/wdt:P625 ?c3 }
      OPTIONAL { ?p wdt:P27/wdt:P36/wdt:P625 ?c5 }
      BIND(COALESCE(?c1, ?c2, ?c3, ?c5) AS ?coord)"""
PERSON = """
      OPTIONAL { ?st pq:P580 ?start } OPTIONAL { ?st pq:P582 ?end }
      OPTIONAL { ?p wdt:P27 ?cit }
      OPTIONAL { ?art schema:about ?p; schema:isPartOf <https://en.wikipedia.org/> }"""


def rows_to_people(rows, extra):
    people = {}
    for b in rows:
        p = qid(v(b, "p"))
        d = people.setdefault(p, {"name": v(b, "pLabel") or p, "desc": v(b, "pDesc"), "offices": {}, "coords": [], "extra": set(),
                                  "country": set(), "article": v(b, "art")})
        pos = v(b, "posLabel")
        if pos:
            yrs = "–".join(x for x in (v(b, "start")[:4], v(b, "end")[:4]) if x)
            d["offices"].setdefault(pos, set())
            if yrs:
                d["offices"][pos].add(yrs)
        m = re.match(r"Point\(([-\d.eE]+) ([-\d.eE]+)\)", v(b, "coord"))
        if m:
            d["coords"].append((round(float(m.group(1)), 5), round(float(m.group(2)), 5)))
        if v(b, "citLabel"):
            d["country"].add(v(b, "citLabel"))
        for k in extra:
            if v(b, k):
                d["extra"].add(v(b, k))
    return people


def features(people, group, captor_word, fixed_branch=None):
    out = []
    for p, d in people.items():
        if not d["coords"]:
            continue
        lon, lat = max(set(d["coords"]), key=d["coords"].count)
        offices = "; ".join(f"{o} ({', '.join(sorted(y))})" if y else o for o, y in sorted(d["offices"].items()))
        out.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]},
                    "properties": {"name": d["name"], "group": TIERS[group], "branch": fixed_branch or branch_of(list(d["offices"])),
                                   "offices held": offices, captor_word: "; ".join(sorted(d["extra"])),
                                   "who they are": d["desc"], "citizenship": "; ".join(sorted(d["country"])),
                                   "Wikidata": f"https://www.wikidata.org/wiki/{p}", "Wikipedia": d["article"],
                                   "source": "Wikidata (CC0), as it stands on " + datetime.date.today().isoformat(),
                                   "placed at": "the place their office covers (or its capital), else their country's capital"}})
    return out


def wikidata(found, errors):
    feats = []
    try:
        agencies = classes(AGENCY_NAMES, found)
        occs = classes(OCCUPATION_NAMES, found)
        biz = classes(BUSINESS_NAMES, found)
    except Exception as e:  # noqa: BLE001
        errors.append(f"kinds: {type(e).__name__}: {e}")
        return feats
    ag = " ".join("wd:" + c for c in agencies)
    oc = " ".join("wd:" + c for c in occs)
    # a. office holders who served a spy service or secret police
    try:
        rows = sparql(f"""SELECT DISTINCT ?p ?pLabel ?pDesc ?pos ?posLabel ?start ?end ?coord ?citLabel ?art ?orgLabel ?occLabel WHERE {{
          {{ VALUES ?k {{ {ag} }} ?org wdt:P31 ?k. ?p wdt:P108|wdt:P463|wdt:P1416 ?org. }}
          UNION {{ VALUES ?occ {{ {oc} }} ?p wdt:P106 ?occ. }}
          ?p wdt:P31 wd:Q5; p:P39 ?st. ?st ps:P39 ?pos. {PERSON} {PLACE}
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,mul,de,fr,es,ru,pl,cs,it,pt". ?p rdfs:label ?pLabel; schema:description ?pDesc. ?pos rdfs:label ?posLabel. ?cit rdfs:label ?citLabel. ?org rdfs:label ?orgLabel. ?occ rdfs:label ?occLabel. }}
        }}""")
        people = rows_to_people(rows, ["orgLabel", "occLabel"])
        feats += features(people, "served", "spy service or role")
        found["a. office holders who served a spy service"] = len(people)
    except Exception as e:  # noqa: BLE001
        errors.append(f"a: {type(e).__name__}: {e}")
    time.sleep(10)
    # b. office holders convicted of spying, treason, bribery and the like
    try:
        rows = sparql(f"""SELECT DISTINCT ?p ?pLabel ?pDesc ?pos ?posLabel ?start ?end ?coord ?citLabel ?art ?crimeLabel WHERE {{
          ?p wdt:P31 wd:Q5; wdt:P1399 ?crime; p:P39 ?st. ?st ps:P39 ?pos.
          ?crime rdfs:label ?cl. FILTER(LANG(?cl) = "en" && REGEX(?cl, "{CRIME_WORDS}", "i")) {PERSON} {PLACE}
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,mul". ?p rdfs:label ?pLabel; schema:description ?pDesc. ?pos rdfs:label ?posLabel. ?cit rdfs:label ?citLabel. ?crime rdfs:label ?crimeLabel. }}
        }}""")
        people = rows_to_people(rows, ["crimeLabel"])
        feats += features(people, "court", "convicted of")
        found["b. office holders convicted"] = len(people)
        found["crimes matched"] = sorted({v(b, "crimeLabel") for b in rows})
    except Exception as e:  # noqa: BLE001
        errors.append(f"b: {type(e).__name__}: {e}")
    time.sleep(10)
    # c. company people convicted of bribery or of spying on companies
    try:
        bz = " ".join("wd:" + c for c in biz)
        rows = sparql(f"""SELECT DISTINCT ?p ?pLabel ?pDesc ?emp ?empLabel ?coord ?citLabel ?art ?crimeLabel WHERE {{
          ?p wdt:P31 wd:Q5; wdt:P1399 ?crime; wdt:P108 ?emp.
          FILTER NOT EXISTS {{ ?p wdt:P39 ?anyoffice }}
          ?crime rdfs:label ?cl. FILTER(LANG(?cl) = "en" && REGEX(?cl, "{CRIME_WORDS}", "i"))
          VALUES ?k {{ {bz} }} ?emp wdt:P31 ?k.
          OPTIONAL {{ ?emp wdt:P159 ?hq. OPTIONAL {{ ?emp p:P159/pq:P625 ?c1 }} OPTIONAL {{ ?hq wdt:P625 ?c2 }} }}
          OPTIONAL {{ ?emp wdt:P17/wdt:P36/wdt:P625 ?c3 }}
          OPTIONAL {{ ?p wdt:P27 ?cit. OPTIONAL {{ ?cit wdt:P36/wdt:P625 ?c5 }} }}
          BIND(COALESCE(?c1, ?c2, ?c3, ?c5) AS ?coord)
          OPTIONAL {{ ?art schema:about ?p; schema:isPartOf <https://en.wikipedia.org/> }}
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,mul". ?p rdfs:label ?pLabel; schema:description ?pDesc. ?emp rdfs:label ?empLabel. ?cit rdfs:label ?citLabel. ?crime rdfs:label ?crimeLabel. }}
        }}""")
        for b in rows:
            b["posLabel"] = {"value": "worked for " + v(b, "empLabel")}
        people = rows_to_people(rows, ["crimeLabel"])
        f = features(people, "court", "convicted of", fixed_branch="company")
        for x in f:
            x["properties"]["placed at"] = "their employer's head office, else its country's capital, else their own country's capital"
        feats += f
        found["c. company people convicted"] = len(people)
    except Exception as e:  # noqa: BLE001
        errors.append(f"c: {type(e).__name__}: {e}")
    return feats


# ---- cases compiled for this map (28 September 2026) ----------------------
# lon, lat, name, tier, branch, captor, what, sources, extra fields
CASES = [
    (-74.0776, 4.5981, "Colombia's Congress: the parapolitics convictions", "court", "lawmaking",
     "Paramilitary death squads (AUC)",
     "Since the scandal broke in 2006, more than 60 congressmen and seven governors have been convicted for using paramilitary intimidation to get elected; some 140 more former congressmen were under investigation (Colombia Reports). Human Rights Watch counted more than 55 current and former members of Congress convicted by its 2014 report. Paramilitaries had signed pacts with politicians to 'refound the motherland'. Demobilised paramilitaries named close to a thousand politicians as accomplices (InSight Crime). In 2024 León Valencia, whose research helped open the cases, counted 86 members of Congress convicted and 50 more investigated: 136, which he describes as half of Congress (Publimetro).",
     ["https://colombiareports.com/parapolitics/", "https://www.hrw.org/world-report/2014/country-chapters/colombia",
      "https://insightcrime.org/news/brief/colombia-election-results-show-persisting-criminal-influence-in-politics/",
      "https://www.publimetro.co/noticias/2024/05/01/la-parapolitica-fue-un-hecho-unico-en-el-mundo-la-mitad-del-congreso-fue-investigado-leon-valencia/"],
     {"years": "2002–2014 (elections of 2002 and 2006 mainly)", "count": "86 convicted, 136 investigated (Valencia, 2024); earlier counts 55 to 61"}),
    (-74.0776, 4.5981, "Colombia's Congress after parapolitics: candidates with ties to illegal groups elected", "ties", "lawmaking",
     "Paramilitary and criminal groups",
     "Of 131 candidates questioned for criminal ties by the Peace and Reconciliation Foundation, 69 won seats (33 Senate, 36 Chamber): investigated for direct ties with criminal groups, or connected to politicians accused or convicted of parapolitics.",
     ["https://insightcrime.org/news/brief/colombia-election-results-show-persisting-criminal-influence-in-politics/"], {"count": "69 elected"}),
    (139.7449, 35.6759, "Japan's ruling party and the Unification Church", "ties", "lawmaking",
     "Unification Church (Family Federation for World Peace and Unification), South Korea",
     "The Liberal Democratic Party's own survey (September 2022): 179 of its 379 national lawmakers had ties with the church and related groups, from attending events to receiving election help; 17 received election help. The party named 121 with substantial ties. The survey did not cover local assembly members.",
     ["https://www.japantimes.co.jp/news/2022/09/08/national/ldp-unification-church-survey/",
      "https://www.marketscreener.com/news/latest/Japan-ruling-party-says-179-of-379-lawmakers-had-interactions-with-Unification-Church-41720694/"],
     {"years": "surveyed 2022", "count": "179 of 379", "share of the body": "47%"}),
    (4.3752, 50.8386, "Qatargate: Antonio Panzeri and Francesco Giorgi (European Parliament)", "admitted", "lawmaking",
     "Qatar and Morocco",
     "Former MEP Panzeri took a plea deal; parliamentary assistant Giorgi admitted to accepting bribes from Qatari officials in exchange for influencing the European Parliament's decisions. About €1.5 million in cash was seized in the December 2022 raids.",
     ["https://en.wikipedia.org/wiki/Qatar_corruption_scandal_at_the_European_Parliament", "https://www.ansa.it/amp/english/news/world/2023/01/18/panzeri-accountant-arrested-in-qatargate-probe_a8037eb5-b081-4f7b-aa5e-515be7a83c3d.html"],
     {"years": "from 2019 (Giorgi's account); raids December 2022"}),
    (4.3752, 50.8386, "Qatargate: Eva Kaili, Marc Tarabella, Andrea Cozzolino, Marie Arena (European Parliament)", "alleged", "lawmaking",
     "Qatar and Morocco (alleged)",
     "Charged in the Qatargate investigation; each denies wrongdoing. No one had been convicted as of the sources' dates. Kaili was a vice-president of the Parliament; Arena was charged in 2025 with belonging to a criminal organisation.",
     ["https://en.wikipedia.org/wiki/Qatar_corruption_scandal_at_the_European_Parliament"], {"status": "charged; they deny it"}),
    (-75.7009, 45.4236, "Canada's Parliament: members said to assist foreign states (NSICOP report)", "inquiry", "lawmaking",
     "China and India, among others (unnamed parliamentarians)",
     "The National Security and Intelligence Committee of Parliamentarians (June 2024) wrote that some elected officials 'began wittingly assisting foreign state actors soon after their election'. It named no one publicly. The public inquiry that followed (Justice Hogue) found the situation 'not as clear cut, nor as extreme' as the report's wording suggested.",
     ["https://www.cbc.ca/news/politics/foreign-interference-trudeau-nsicop-1.7222730",
      "https://www.cbc.ca/news/politics/final-report-public-inquiry-foregin-interference-1.7443597"], {"years": "report 2024", "status": "disputed by the public inquiry"}),
    (-98.58, 39.83, "United States: state laws copied from bills written by industry and advocacy groups", "ties", "lawmaking",
     "Industry groups, ALEC and other model-bill writers",
     "USA Today, the Arizona Republic and the Center for Public Integrity compared nearly a million bills: at least 10,000 bills introduced over eight years were copied almost entirely from model legislation, and more than 2,100 became law. By author: 4,301 industry, 4,012 conservative groups, 1,602 liberal groups, 248 others. Placed at the middle of the country: it covers all 50 state legislatures.",
     ["https://publicintegrity.org/politics/state-politics/copy-paste-legislate/you-elected-them-to-write-new-laws-theyre-letting-corporations-do-it-instead/",
      "https://morrisoninstitute.asu.edu/blog/az-among-top-states-passing-copycat-bills-written-national-partisan-industry-groups"],
     {"years": "about 2011–2019", "count": "10,000+ bills, 2,100+ laws"}),
    (13.3762, 52.5186, "Gregor Gysi (Bundestag)", "inquiry", "lawmaking", "Stasi (East German secret police)",
     "In 1998 the Bundestag's immunity committee concluded he had collaborated with the Stasi from 1978 to 1989 under the name IM Notar. He denies it.",
     ["https://en.wikipedia.org/wiki/Gregor_Gysi"], {"status": "committee finding; he denies it"}),
    (13.3762, 52.5186, "Lutz Heilmann (Bundestag)", "archive", "lawmaking", "Stasi (East German secret police)",
     "Elected in 2005; revealed as a full-time Stasi employee from 1985 to 1990, the only full-time Stasi employee elected to the Bundestag.",
     ["https://en.wikipedia.org/wiki/Lutz_Heilmann"], {"years": "Stasi 1985–1990; MP 2005–2009"}),
    (13.0645, 52.3906, "Lothar Bisky (Volkskammer, Brandenburg parliament, Bundestag)", "archive", "lawmaking", "Stasi (East German secret police)",
     "Stasi records list him as an informer under the code names Bienert (1966–1970) and Klaus Heine (from 1987), described as reliable.",
     ["https://en.wikipedia.org/wiki/Lothar_Bisky"], {}),
    (13.3762, 52.5186, "Diether Dehm (Bundestag)", "archive", "lawmaking", "Stasi (East German secret police)",
     "Stasi files show he reported to the Stasi, including on the SPD, West German artists and the University of Frankfurt, and on Wolf Biermann in 1976.",
     ["https://en.wikipedia.org/wiki/Diether_Dehm"], {}),
    (7.0982, 50.7374, "West Germany: the Stasi's agents and wiretaps", "archive", "ruling and running", "Stasi foreign intelligence (HVA)",
     "The Stasi's foreign intelligence service recruited 20,000 to 30,000 agents in West Germany during the Cold War, and listened to the phone calls of the West German president, the heads of its security services, senior officials in Bonn and all members of the Bundestag (CIA review of the Stasi archive's own study). In 2010 the Stasi archive was asked to check about 2,000 people who sat in the Bundestag between 1949 and 1989.",
     ["https://www.cia.gov/resources/csi/static/West-Arbeit-des-MfS.pdf",
      "https://www.osw.waw.pl/en/publikacje/analyses/2010-10-13/gauck-office-will-investigate-links-between-bundestag-and-stasi"], {"years": "1950–1989", "count": "20,000–30,000 agents"}),
    (-99.1332, 19.4326, "Genaro García Luna (Mexico's Secretary of Public Security)", "court", "ruling and running", "Sinaloa Cartel",
     "Convicted by a US jury in February 2023 and sentenced to 460 months for taking millions of dollars in bribes from the Sinaloa Cartel while he ran Mexico's fight against it (2006–2012); his police leaked information to the cartel. He denied it.",
     ["https://www.justice.gov/usao-edny/pr/ex-mexican-secretary-public-security-genaro-garcia-luna-sentenced-over-38-years"], {"years": "2006–2012"}),
    (-79.5199, 8.9824, "Manuel Noriega (ruler of Panama)", "admitted", "ruling and running", "CIA and the US Army",
     "US prosecutors' 1991 court filings acknowledged that Noriega was a paid asset of the US Army and had a paid relationship with the CIA, confirming payments of $300,162; he supplied information including Panama's position in the Canal treaty talks. He ruled Panama 1983–1989.",
     ["https://www.tampabay.com/archive/1991/05/31/noriega-worked-for-cia/", "https://www.cia.gov/readingroom/document/cia-rdp99-00418r000100370026-4"],
     {"years": "from the 1960s or 70s to the 1980s"}),
    (-75.8813, 41.2459, "The kids-for-cash judges: Mark Ciavarella and Michael Conahan (Luzerne County, Pennsylvania)", "court", "courts",
     "The builder and co-owner of two for-profit youth detention centres",
     "The judges shut the county's own juvenile detention centre and took $2.8 million in illegal payments from the builder and co-owner of two private lockups, then filled them with children. Ciavarella was convicted of racketeering (28 years); Conahan pleaded guilty. The Pennsylvania Supreme Court threw out about 4,000 of Ciavarella's juvenile rulings (2003–2008).",
     ["https://witf.org/2020/08/26/kids-for-cash-judge-from-luzerne-county-loses-bid-for-lighter-prison-sentence",
      "https://www.nbcnews.com/id/wbna44105072"], {"years": "2003–2008"}),
]
# Odebrecht's plea: the twelve countries it named, each at its capital.
ODEBRECHT = [("Angola", 13.2344, -8.8390), ("Argentina", -58.3816, -34.6037), ("Brazil", -47.8825, -15.7942), ("Colombia", -74.0721, 4.7110),
             ("Dominican Republic", -69.9312, 18.4861), ("Ecuador", -78.4678, -0.1807), ("Guatemala", -90.5069, 14.6349), ("Mexico", -99.1332, 19.4326),
             ("Mozambique", 32.5732, -25.9692), ("Panama", -79.5199, 8.9824), ("Peru", -77.0428, -12.0464), ("Venezuela", -66.9036, 10.4806)]
for c, lon, lat in ODEBRECHT:
    CASES.append((lon, lat, f"Odebrecht's bribes to officials in {c}", "admitted", "company",
                  "Odebrecht (Brazilian construction company) and Braskem",
                  "In its December 2016 guilty plea in the United States, Odebrecht admitted paying about $788 million in bribes to officials and political parties, through a division that worked as a bribery department, for more than 100 projects in twelve countries (Angola, Argentina, Brazil, Colombia, Dominican Republic, Ecuador, Guatemala, Mexico, Mozambique, Panama, Peru, Venezuela), from 2001 to 2016, gaining about $3.336 billion. This point marks the officials of " + c + "; the plea does not name them.",
                  ["https://justice.gov/opa/press-release/file/919911/download", "https://fcpa.stanford.edu/enforcement-action.html?id=635"],
                  {"years": "2001–2016", "placed at": "the capital of " + c}))
CASES.append((-38.5014, -12.9714, "Odebrecht, Salvador, Brazil", "admitted", "company", "Odebrecht itself (the captor)",
              "The company that admitted paying about $788 million in bribes in twelve countries (2001–2016). Its former head Marcelo Odebrecht was sentenced to 19 years in Brazil for bribes to Petrobras executives.",
              ["https://justice.gov/opa/press-release/file/919911/download", "https://en.wikipedia.org/wiki/Odebrecht"], {"years": "2001–2016"}))

# Colombia: members of Congress convicted in the parapolitics cases, by name,
# as the sources below print them (each at the Capitolio Nacional, Bogotá).
_VA = "https://www.las2orillas.co/?p=25389"
COLOMBIA = [
    # (name, tier, what, source)
    *[(n, "court", "Listed among members of Congress convicted by the Supreme Court for parapolitics (Cambio Radical senators), in Verdad Abierta's count of the Court's sentences as reported by Las2orillas.", _VA)
      for n in ["Humberto Builes Correa", "Rubén Darío Quintero", "Reginaldo Montes", "Jairo Enrique Merlano", "Javier Cáceres Leal"]],
    *[(n, "court", "Listed among members of Congress convicted by the Supreme Court for parapolitics (Cambio Radical representatives), in Verdad Abierta's count of the Court's sentences as reported by Las2orillas.", _VA)
      for n in ["Fabio Arango Torres", "José María Conde Romero", "Oscar Leonidas Wilches Carreño", "Edgar Eulises Torres Murillo", "Jesús Enrique Doval Urango",
                "Estanislao Ortiz Lara", "Jaime Cervantes Valero", "César Augusto Andrade", "Manuel Darío Ávila Peralta"]],
    *[(n, "court", "Listed among members of Congress convicted by the Supreme Court for parapolitics (Liberal Party), in Verdad Abierta's count of the Court's sentences as reported by Las2orillas.", _VA)
      for n in ["Juan Manuel López Cabrales", "Mario Salomón Náder"]],
    ("Enrique Rafael Caballero", "court", "Sentenced by the Supreme Court to five years and seven months after accepting ties with paramilitary chief Hernán Giraldo Serna in the campaign that took him to Congress in 2002.", "https://cooperativa.cl/noticias/mundo/colombia/justicia-condeno-a-prision-a-otro-politico-colombiano-por-nexos-con/2011-03-10/021804.html"),
    ("Álvaro García Romero", "court", "Given the heaviest sentence, 40 years, for his part in the Macayepo massacre, in which Sucre paramilitaries killed 15 farmworkers.", _VA),
    ("Mario Uribe Escobar", "court", "Former president of Congress and cousin of President Álvaro Uribe; convicted for ties with the AUC paramilitaries.", "https://en.wikipedia.org/wiki/Colombian_parapolitics_scandal"),
    ("Miguel Pinedo", "court", "Former member of Congress convicted for parapolitics.", "https://accounter.co/noticias/actualidad/las-perlas-de-las-megapensiones__trashed"),
    ("Ramón Antonio Valencia", "court", "Former member of Congress sentenced to 45 months for ties with paramilitary groups.", "https://accounter.co/noticias/actualidad/las-perlas-de-las-megapensiones__trashed"),
    ("José María Imbett", "court", "Former member of Congress convicted for parapolitics.", "https://accounter.co/noticias/actualidad/las-perlas-de-las-megapensiones__trashed"),
    ("Vicente Blel Saad", "court", "Former senator convicted for parapolitics.", "https://www.las2orillas.co/?p=27326"),
    ("Ciro Ramírez", "court", "Sentenced to seven years for ties with the AUC's Bloque Central Bolívar.", "https://www.las2orillas.co/?p=27326"),
    ("Alirio Villamizar", "court", "Former member of Congress for Norte de Santander, convicted for parapolitics.", "https://www.las2orillas.co/?p=27326"),
    ("Óscar Suárez Mira", "court", "Sentenced in January 2011 to nine years for ties with the Autodefensas del Urabá Antioqueño.", "https://www.las2orillas.co/?p=27326"),
    ("Luis Alberto Gil Castillo", "court", "Former senator sentenced by the Supreme Court to seven and a half years for accepting electoral support from paramilitary leader Iván Roberto Duque ('Ernesto Báez').", "https://telemedellin.tv/?p=3092"),
    ("Óscar Reyes", "court", "Sentenced by the Supreme Court for ties with paramilitary leaders including Carlos Castaño and Salvatore Mancuso to fund his 2006 campaign.", "https://telemedellin.tv/?p=3092"),
    ("Eric Morris", "court", "Among the first members of Congress convicted in the parapolitics cases.", "https://www.eltiempo.com/archivo/documento/cms-3930608"),
    ("Alfonso Campo Escobar", "court", "Convicted; he accepted an early sentence.", "https://www.eltiempo.com/archivo/documento/cms-3930608"),
    ("Dieb Maloof", "court", "Among the first members of Congress convicted in the parapolitics cases.", "https://www.eltiempo.com/archivo/documento/cms-3930608"),
    ("Rocío Arias", "admitted", "Accepted an early sentence after her arrest (El Tiempo).", "https://www.eltiempo.com/archivo/documento/cms-3930608"),
]
for n, tier, what, src in COLOMBIA:
    CASES.append((-74.0762, 4.5975, n + " (Congress of Colombia)", tier, "lawmaking", "Paramilitary groups (AUC and allied blocs)",
                  what, [src], {"placed at": "the Capitolio Nacional, Bogotá"}))
CASES.append((14.4205, 50.0907, "Andrej Babiš (Czech prime minister 2017–2021)", "archive", "ruling and running", "StB (Czechoslovak secret police)",
              "The StB's records, held by Slovakia's Nation's Memory Institute, register him as a secret collaborator. Historians told a Slovak court the records are credible and meet every requirement for a registered collaborator; he denies collaborating and has sued over the records.",
              ["https://www.e15.cz/domaci/zaznamy-o-babisove-spolupraci-s-stb-jsou-verohodne-rekli-u-soudu-historici-1085015"], {"status": "in the StB records; he denies it"}))

# ---- lists read each week --------------------------------------------------
import html as _html
from html.parser import HTMLParser

SKIP_HEADINGS = r"^(see also|references|notes|further reading|external links|bibliography|sources|citations|literatura|referencias|véase también|enlaces externos|notas|bibliografía)$"
SKIP_CLASSES = ("navbox", "reflist", "references", "toc", "sidebar", "infobox", "mw-editsection", "hatnote", "metadata", "catlinks")


class ListReader(HTMLParser):
    """Every list item of a Wikipedia page, with the heading it sits under and
    its first link; items in reference lists, navigation boxes and the like are
    left out."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.heading, self.in_h, self.htext = "", False, ""
        self.stack, self.items, self.li = [], [], None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        skip = any(c in (a.get("class") or "") for c in SKIP_CLASSES)
        if tag in ("h2", "h3", "h4"):
            self.in_h, self.htext = True, ""
        if tag not in ("br", "img", "hr", "meta", "link", "input", "wbr"):
            self.stack.append((tag, skip))
        if tag == "li" and not any(sk for _, sk in self.stack):
            self.li = {"heading": self.heading, "text": "", "link": None, "depth": len(self.stack)}
        if tag == "a" and self.li is not None and self.li["link"] is None:
            h = a.get("href") or ""
            if h.startswith("/wiki/") and ":" not in h[6:]:
                self.li["link"] = urllib.parse.unquote(h[6:]).replace("_", " ")

    def handle_endtag(self, tag):
        if tag in ("h2", "h3", "h4") and self.in_h:
            self.in_h, self.heading = False, re.sub(r"\s+", " ", self.htext).replace("[edit]", "").strip()
        while self.stack:
            t, _ = self.stack.pop()
            if t == tag:
                break
        if tag == "li" and self.li is not None and len(self.stack) < self.li["depth"]:
            self.li["text"] = re.sub(r"\[\d+\]|\s+", " ", self.li["text"]).strip()
            self.items.append(self.li)
            self.li = None

    def handle_data(self, d):
        if self.in_h:
            self.htext += d
        if self.li is not None:
            self.li["text"] += d


def wiki_items(lang, titles):
    for t in titles:
        try:
            url = f"https://{lang}.wikipedia.org/w/api.php?" + urllib.parse.urlencode({"action": "parse", "page": t, "prop": "text", "formatversion": 2, "format": "json", "redirects": 1})
            j = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA["User-Agent"]}), timeout=120).read())
            if "parse" not in j:
                continue
            r = ListReader()
            r.feed(j["parse"]["text"])
            items = [i for i in r.items if i["text"] and not re.match(SKIP_HEADINGS, i["heading"].lower())]
            return j["parse"]["title"], items
        except Exception as e:  # noqa: BLE001
            print(f"  {lang}:{t}: {type(e).__name__}: {e}", flush=True)
    return None, []


def wiki_url(lang, title):
    return f"https://{lang}.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"), safe="/:()',!*$;@-._~")


def people_by_article(lang, titles):
    """Wikidata's record for each article: description, citizenship and its
    capital's coordinates, offices held."""
    out = {}
    titles = sorted(set(t for t in titles if t))
    for i in range(0, len(titles), 60):
        vals = " ".join("<" + wiki_url(lang, t) + ">" for t in titles[i:i + 60])
        try:
            rows = sparql(f"""SELECT ?art ?p ?d ?coord ?cl (GROUP_CONCAT(DISTINCT ?pl; separator="|") AS ?offices) WHERE {{
              VALUES ?art {{ {vals} }} ?art schema:about ?p.
              OPTIONAL {{ ?p schema:description ?d FILTER(LANG(?d) = "en") }}
              OPTIONAL {{ ?p wdt:P27 ?cit. ?cit wdt:P36/wdt:P625 ?coord. OPTIONAL {{ ?cit rdfs:label ?cl FILTER(LANG(?cl) = "en") }} }}
              OPTIONAL {{ ?p wdt:P39 ?pos. ?pos rdfs:label ?pl FILTER(LANG(?pl) = "en") }}
            }} GROUP BY ?art ?p ?d ?coord ?cl""")
        except Exception as e:  # noqa: BLE001
            print(f"  people_by_article: {type(e).__name__}: {e}", flush=True)
            continue
        for b in rows:
            t = urllib.parse.unquote(v(b, "art").split("/wiki/", 1)[1]).replace("_", " ")
            if t in out and out[t].get("coord"):
                continue
            m = re.match(r"Point\(([-\d.eE]+) ([-\d.eE]+)\)", v(b, "coord"))
            out[t] = {"qid": qid(v(b, "p")), "desc": v(b, "d"), "country": v(b, "cl"),
                      "coord": (round(float(m.group(1)), 5), round(float(m.group(2)), 5)) if m else None,
                      "offices": [o for o in v(b, "offices").split("|") if o]}
        time.sleep(2)
    return out


def list_features(lang, items, tier, captor, fallback, fallback_note, source, extra_of=None):
    info = people_by_article(lang, [i["link"] for i in items])
    feats = []
    for it in items:
        name = it["link"] or it["text"].split(",")[0][:120]
        w = info.get(it["link"] or "", {})
        lonlat = w.get("coord") or fallback
        br = branch_of(w.get("offices", []) + [it["text"]])
        if br == "other office" and not w.get("offices"):
            br = "no office recorded"
        props = {"name": name, "group": TIERS[tier], "branch": br,
                 "working for or tied to": captor, "what the list says": it["text"], "section": it["heading"],
                 "offices held (Wikidata)": "; ".join(w.get("offices", [])), "who they are": w.get("desc", ""), "citizenship": w.get("country", ""),
                 "Wikipedia": wiki_url(lang, it["link"]) if it["link"] else "", "Wikidata": f"https://www.wikidata.org/wiki/{w['qid']}" if w.get("qid") else "",
                 "source": source, "placed at": "the capital of their country (Wikidata)" if w.get("coord") else fallback_note}
        if extra_of:
            props.update(extra_of(it))
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": list(lonlat)}, "properties": props})
    return feats


def venona(found, errors):
    title, items = wiki_items("en", ["List of Americans in the Venona papers"])
    items = [i for i in items if i["link"] and re.search(r"^list$|^[a-z]$|^[a-z]–[a-z]$|names", i["heading"].lower() or "list")] or [i for i in items if i["link"]]
    found["venona items"] = len(items)
    if not items:
        errors.append("venona: nothing read")
        return []
    return list_features("en", items, "archive", "Soviet intelligence (NKVD/KGB and GRU), as read in the Venona decrypts",
                         (-77.0365, 38.8977), "Washington: the decrypts concern Soviet sources in the United States; no country found for this person",
                         f"Wikipedia, {title} (CC BY-SA 4.0), from Haynes and Klehr's reading of the Venona decrypts; how far some named were involved is disputed",
                         lambda it: {"identity": "inferred by researchers (marked ** on the list)" if "**" in it["text"] else "as named in the decrypts"})


def mitrokhin(found, errors):
    title, items = wiki_items("en", ["Mitrokhin Archive"])
    keep = [i for i in items if i["link"] and re.search(r"expos|agent|spies|spy|named|revel|alleg|politic|influence|countr|kingdom|italy|india|germany|france|united|japan", i["heading"].lower())]
    found["mitrokhin items"] = len(keep)
    found["mitrokhin headings"] = sorted({i["heading"] for i in items})
    if not keep:
        errors.append("mitrokhin: nothing read")
        return []
    return list_features("en", keep, "archive", "KGB, as recorded in Vasili Mitrokhin's notes",
                         (0.1051, 52.2066), "Churchill Archives Centre, Cambridge, where Mitrokhin's notes are kept; no country found for this person",
                         f"Wikipedia, {title} (CC BY-SA 4.0). The notes are Mitrokhin's handwritten copies of KGB files; the originals have not been seen by independent historians, and several people named deny it")


def colombia_wiki(found, errors):
    title, items = wiki_items("es", ["Parapolítica", "Escándalo de la parapolítica"])
    found["colombia es.wikipedia headings"] = sorted({i["heading"] for i in items})
    keep = [i for i in items if i["link"] and re.search(r"conden|investig|implic|involucr|vincul|congres|senad|represent|gobernad", i["heading"].lower())]
    found["colombia items"] = len(keep)
    if not keep:
        errors.append("colombia: no list sections found on es.wikipedia (see the headings in build.json)")
        return []
    return list_features("es", keep, "court", "Paramilitary groups (AUC and allied blocs)", (-74.0762, 4.5975),
                         "the Capitolio Nacional, Bogotá",
                         f"Spanish Wikipedia, {title} (CC BY-SA 4.0)",
                         lambda it: {"group": TIERS["court"] if re.search(r"conden", it["heading"].lower()) else TIERS["alleged"]})


# ---- US Securities and Exchange Commission: every FCPA case it lists ---------
SEC_PAGE = "https://www.sec.gov/about/divisions-offices/division-enforcement/enforcement-topics-initiatives/sec-enforcement-actions-fcpa-cases"
SEC_ALIASES = {"UAE": "United Arab Emirates", "U.A.E.": "United Arab Emirates", "Korea": "South Korea", "Türkiye": "Turkey",
               "Ivory Coast": "Côte d'Ivoire", "Czech Republic": "Czech Republic", "Macao": "China", "Macau": "China", "Hong Kong": "China"}


def countries(found):
    rows = sparql("""SELECT ?c ?l ?alt ?coord WHERE {
      ?c wdt:P31 wd:Q6256; wdt:P36 ?cap. ?cap wdt:P625 ?coord. ?c rdfs:label ?l FILTER(LANG(?l) = "en")
      OPTIONAL { ?c skos:altLabel ?alt FILTER(LANG(?alt) = "en") } }""")
    names = {}
    for b in rows:
        m = re.match(r"Point\(([-\d.eE]+) ([-\d.eE]+)\)", v(b, "coord"))
        if not m:
            continue
        ll = (round(float(m.group(1)), 5), round(float(m.group(2)), 5))
        names.setdefault(v(b, "l"), (v(b, "l"), ll))
        a = v(b, "alt")
        if a and len(a) > 3 and a[0].isupper():
            names.setdefault(a, (v(b, "l"), ll))
    for a, to in SEC_ALIASES.items():
        if to in names:
            names[a] = names[to]
    found["country names"] = len(names)
    return names


def sec_fcpa(found, errors):
    try:
        page = urllib.request.urlopen(urllib.request.Request(SEC_PAGE, headers={"User-Agent": UA["User-Agent"]}), timeout=120).read().decode("utf-8", "replace")
        names = countries(found)
    except Exception as e:  # noqa: BLE001
        errors.append(f"sec: {type(e).__name__}: {e}")
        return []
    body = page.split("listed by calendar year", 1)[-1]
    rx = sorted(names, key=len, reverse=True)
    pat = re.compile(r"(?<![A-Za-z])(" + "|".join(re.escape(n) for n in rx) + r")(?![A-Za-z])")
    feats, year = [], ""
    for part in re.split(r"(<h2[^>]*>.*?</h2>|<li[^>]*>.*?</li>|<p[^>]*>\s*\d{4}\s*</p>)", body, flags=re.S):
        if part.startswith("<h2") or part.startswith("<p"):
            y = re.search(r"(19|20)\d\d|Previous Years", re.sub("<[^>]+>", "", part))
            if y:
                year = y.group(0)
            continue
        if not part.startswith("<li"):
            continue
        a = re.search(r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', part, re.S)
        text = _html.unescape(re.sub(r"\s+", " ", re.sub("<[^>]+>", "", part))).strip()
        if not text or len(text) < 4:
            continue
        who = _html.unescape(re.sub("<[^>]+>", "", a.group(2))).strip() if a else text.split(" – ")[0].split(" (")[0]
        link = urllib.parse.urljoin(SEC_PAGE, a.group(1)) if a else SEC_PAGE
        date = (re.findall(r"\((\d{1,2}/\d{1,2}/\d{2,4})\)", text) or re.findall(r"(\d{1,2}/\d{1,2}/\d{2,4})", text) or [year])[0]
        low = text.lower()
        tier = "admitted" if "pleaded guilty" in low or "admitted" in low and "without admitting" not in low else "court" if "convicted" in low \
            else "settled" if re.search(r"agreed|settle|ordered to pay|to pay|disgorge|penalty|non-prosecution|deferred prosecution", low) else "alleged"
        found_c = []
        for m in pat.finditer(text.replace(who, " ")):
            c = names[m.group(1)]
            if c[0] != "United States of America" and c not in found_c:
                found_c.append(c)
        base = {"group": TIERS[tier], "branch": "company", "working for or tied to": who, "what the SEC says": text, "date": date, "year": year,
                "SEC release": link, "note": "" if len(text) > 60 else "The listing gives only the name and date; the SEC release has the outcome.", "source": "US Securities and Exchange Commission, SEC Enforcement Actions: FCPA Cases (public domain), read " + datetime.date.today().isoformat()}
        if not found_c:
            feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [-77.0038, 38.8977]},
                          "properties": dict(base, name=f"{who}: bribery case (no country named in the listing)",
                                             **{"placed at": "the SEC in Washington: the listing names no country"})})
        for cname, ll in found_c:
            feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": list(ll)},
                          "properties": dict(base, name=f"{who}: bribes to officials in {cname}", country=cname,
                                             **{"placed at": f"the capital of {cname}, where the SEC says the bribes or improper payments were made"})})
    found["sec cases"] = len({f["properties"]["what the SEC says"] for f in feats})
    found["sec points"] = len(feats)
    if not feats:
        errors.append("sec: no cases read (page layout changed?)")
    return feats


# ---- US Justice Department: every FCPA and related case it lists (round 110c)
DOJ_YEAR = "https://www.justice.gov/criminal/criminal-fraud/related-enforcement-actions-chronological-list-{}"
DISTRICTS = {  # court district -> the city its court sits in (the listing names no country)
    "district of columbia": ("Washington, DC", -77.0365, 38.8977), "southern district of new york": ("New York", -74.0026, 40.7143),
    "eastern district of new york": ("Brooklyn", -73.9903, 40.6958), "eastern district of virginia": ("Alexandria, Virginia", -77.0469, 38.8048),
    "southern district of texas": ("Houston", -95.3698, 29.7604), "southern district of florida": ("Miami", -80.1918, 25.7617),
    "district of new jersey": ("Newark", -74.1724, 40.7357), "northern district of illinois": ("Chicago", -87.6298, 41.8781),
    "central district of california": ("Los Angeles", -118.2437, 34.0522), "district of massachusetts": ("Boston", -71.0589, 42.3601),
    "district of connecticut": ("New Haven", -72.9279, 41.3083), "northern district of oklahoma": ("Tulsa", -95.9928, 36.154),
    "eastern district of texas": ("Sherman, Texas", -96.6089, 33.6357), "district of maryland": ("Baltimore", -76.6122, 39.2904),
    "southern district of california": ("San Diego", -117.1611, 32.7157), "northern district of california": ("San Francisco", -122.4194, 37.7749),
    "eastern district of pennsylvania": ("Philadelphia", -75.1652, 39.9526), "western district of texas": ("San Antonio", -98.4936, 29.4241),
    "district of minnesota": ("Minneapolis", -93.265, 44.9778), "northern district of georgia": ("Atlanta", -84.388, 33.749),
    "middle district of florida": ("Tampa", -82.4572, 27.9506), "northern district of texas": ("Dallas", -96.797, 32.7767),
    "district of puerto rico": ("San Juan", -66.1057, 18.4655), "western district of washington": ("Seattle", -122.3321, 47.6062),
}


def doj_fcpa(found, errors):
    feats, years = [], range(1977, datetime.date.today().year + 1)
    for y in years:
        try:
            page = urllib.request.urlopen(urllib.request.Request(DOJ_YEAR.format(y), headers={"User-Agent": UA["User-Agent"]}), timeout=90).read().decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            found.setdefault("doj years not read", []).append(f"{y}: {type(e).__name__}")
            continue
        body = page.split("Chronological List, " + str(y), 1)[-1].split("Report an FCPA", 1)[0]
        lines = [x for x in (re.sub(r"\s+", " ", _html.unescape(l)).strip() for l in re.sub(r"<[^>]+>", "\n", body).split("\n")) if x]
        case = None
        for l in lines + ["United States v. END"]:
            if re.match(r"^(United States|U\.S\.|USA) v\.|^In Re |^In re ", l):
                if case:
                    feats.append(case)
                case = {"title": l, "docket": "", "district": "", "filed": "", "year": y}
            elif case is not None:
                m = re.match(r"(Docket No|District|Filed|Announced on)\s*:?\s*(.*)", l)
                if m:
                    k = {"Docket No": "docket", "District": "district", "Filed": "filed", "Announced on": "filed"}[m.group(1)]
                    case[k] = m.group(2)
                elif not case["docket"] and not case["district"] and len(case["title"]) < 200:
                    case["title"] += " " + l
        time.sleep(1)
    out = []
    for c in feats:
        if c["title"] == "United States v. END":
            continue
        d = DISTRICTS.get(c["district"].lower().strip())
        where, lon, lat = d if d else ("Washington, DC", -77.0365, 38.8977)
        tier = "settled" if c["title"].lower().startswith("in re") else "alleged"
        out.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]},
                    "properties": {"name": c["title"], "group": TIERS[tier], "branch": "company",
                                   "working for or tied to": "bribery of foreign officials (US Foreign Corrupt Practices Act and related laws)",
                                   "docket": c["docket"], "court district": c["district"], "filed or announced": c["filed"], "year": c["year"],
                                   "note": ("An 'In re' entry is a resolution the Justice Department announced without charges in court (a non-prosecution agreement, declination or the like)."
                                            if tier == "settled" else "A case filed by the Justice Department; the listing does not give the outcome. Many ended in guilty pleas; the case page has the filings."),
                                   "DOJ list": DOJ_YEAR.format(c["year"]),
                                   "source": "US Department of Justice, FCPA and related enforcement actions, chronological list (public domain), read " + datetime.date.today().isoformat(),
                                   "placed at": (f"{where}, where the court for this district sits; the listing names no country" if d else "Washington, DC (the Justice Department); the listing names no district we could place")}})
    found["doj cases"] = len(out)
    if not out:
        errors.append("doj: no cases read (page layout changed?)")
    return out


# ---- secret-police collaborators by Wikipedia category (round 110c) --------
# Each Wikipedia's own category of people the secret police registered; each
# article cites the archive record behind it.
CATEGORY_WIKIS = [
    ("cs", ["Státní bezpečnost spolupracovníci", "agenti StB"], r"(agent|spolupracovní|informátor|konfident).*(státní bezpečnost|stb)", (14.4205, 50.0875), "StB (Czechoslovak secret police)"),
    ("sk", ["spolupracovníci Štátnej bezpečnosti", "agenti ŠtB"], r"(agent|spolupracovní).*(štátnej bezpečnosti|štb)", (17.1077, 48.1486), "ŠtB (Czechoslovak secret police)"),
    ("pl", ["tajni współpracownicy aparatu bezpieczeństwa", "tajni współpracownicy SB"], r"(tajni współpracownicy|współpracownicy|agenci).*(bezpiecze|sb|ub|wywiad)", (21.0122, 52.2297), "Polish communist-era security services"),
    ("de", ["Inoffizieller Mitarbeiter des Ministeriums für Staatssicherheit"], r"inoffizielle[rn]? mitarbeiter", (13.4050, 52.5200), "Stasi (East German secret police)"),
    ("ro", ["informatori ai Securității", "colaboratori ai Securității"], r"(informatori|colaboratori|agenți).*securit", (26.1025, 44.4268), "Securitate (Romanian secret police)"),
    ("bg", ["агенти на Държавна сигурност", "сътрудници на Държавна сигурност"], r"(агент|сътрудни).*(държавна сигурност|дс)", (23.3219, 42.6977), "Committee for State Security (Bulgaria)"),
]


def wapi(lang, **q):
    q.update({"format": "json", "formatversion": 2})
    url = f"https://{lang}.wikipedia.org/w/api.php?" + urllib.parse.urlencode(q)
    return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA["User-Agent"]}), timeout=120).read())


def category_members(lang, cat, depth=1):
    out, cont = [], {}
    while True:
        j = wapi(lang, action="query", list="categorymembers", cmtitle=cat, cmlimit=500, cmtype="page|subcat", **cont)
        for m in j.get("query", {}).get("categorymembers", []):
            if m["ns"] == 0:
                out.append(m["title"])
            elif m["ns"] == 14 and depth > 0:
                out += category_members(lang, m["title"], depth - 1)
        if "continue" not in j:
            return out
        cont = {"cmcontinue": j["continue"]["cmcontinue"]}


def secret_police_categories(found, errors):
    feats = []
    for lang, terms, rx, fallback, captor in CATEGORY_WIKIS:
        try:
            cats = set()
            for term in terms:
                j = wapi(lang, action="query", list="search", srsearch=term, srnamespace=14, srlimit=50)
                cats |= {r["title"] for r in j.get("query", {}).get("search", []) if re.search(rx, r["title"].lower())}
            titles = {}
            for c in sorted(cats):
                for t in category_members(lang, c):
                    titles.setdefault(t, c)
            found[f"{lang} categories"] = {c: sum(1 for x in titles.values() if x == c) for c in sorted(cats)}
            if not titles:
                continue
            items = [{"link": t, "text": t, "heading": c} for t, c in titles.items()]
            got = list_features(lang, items, "archive", captor, fallback, "the capital of the country whose secret police it was (no citizenship found in Wikidata)",
                                f"{lang}.wikipedia category (CC BY-SA 4.0); each article cites the archive record behind it",
                                lambda it: {"category": it["heading"]})
            for f in got:
                f["properties"].pop("what the list says", None)
            feats += got
        except Exception as e:  # noqa: BLE001
            errors.append(f"categories {lang}: {type(e).__name__}: {e}")
        time.sleep(2)
    return feats


def ipn(found, errors):
    p = OUT / "ipn.geojson"
    if not p.exists():
        errors.append("ipn: not built yet (scripts/capture_ipn.py reads the catalogue a slice a day)")
        return []
    got = json.loads(p.read_text())["features"]
    found["ipn drawn"] = len(got)
    return got


# ---- probes: pages saved for the next round to read ------------------------
PROBES = {
    "ipn_catalogue_entry_86435.html": "https://katalog.bip.ipn.gov.pl/informacje/86435",
    "abs_registers.html": "https://www.abscr.cz/cs/vyhledavani-archivni-pomucky",
    "abs_home.html": "https://www.abscr.cz/",
    "upn_regpro.html": "https://www.upn.gov.sk/regpro/",
    "upn_home.html": "https://www.upn.gov.sk/",
}


def probes(found):
    d = pathlib.Path("probe/capture")
    d.mkdir(parents=True, exist_ok=True)
    got = {}
    for name, url in PROBES.items():
        try:
            r = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA["User-Agent"]}), timeout=90)
            data = r.read()
            (d / name).write_bytes(data)
            got[name] = {"url": url, "final": r.geturl(), "status": r.status, "bytes": len(data)}
        except Exception as e:  # noqa: BLE001
            got[name] = {"url": url, "error": f"{type(e).__name__}: {e}"}
    (d / "index.json").write_text(json.dumps(got, indent=1, ensure_ascii=False))
    found["probes"] = got


def compiled():
    out = []
    for lon, lat, name, tier, branch, captor, what, srcs, extra in CASES:
        props = {"name": name, "group": TIERS[tier], "branch": branch, "working for or tied to": captor, "what the record says": what,
                 "sources": " ".join(srcs), "source": "Compiled for this map on 28 September 2026 from the sources listed"}
        props.update(extra)
        out.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]}, "properties": props})
    return out


def main():
    stamp = OUT / "build.json"
    if stamp.exists() and datetime.date.today().weekday() != 0 and os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
        print("capture: weekly; not Monday")
        return
    OUT.mkdir(exist_ok=True)
    found, errors = {}, []
    wd = wikidata(found, errors)
    lists = []
    old = OUT / "cases.geojson"
    before = json.loads(old.read_text())["features"] if old.exists() else []
    for job in (venona, mitrokhin, colombia_wiki, sec_fcpa, doj_fcpa, secret_police_categories, ipn):
        try:
            got = job(found, errors)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{job.__name__}: {type(e).__name__}: {e}")
            got = []
        for f in got:
            f["properties"]["part"] = job.__name__
        if not got:
            got = [f for f in before if f["properties"].get("part") == job.__name__]
            if got:
                errors.append(f"{job.__name__}: kept {len(got)} from the last build")
        found[job.__name__ + " features"] = len(got)
        lists += got
    try:
        probes(found)
    except Exception as e:  # noqa: BLE001
        errors.append(f"probes: {type(e).__name__}: {e}")
    feats = compiled() + wd + lists
    had_old = old.exists()
    if not wd and had_old:
        # Wikidata did not answer: keep last week's Wikidata part.
        prev = [f for f in before if f["properties"].get("source", "").startswith("Wikidata (CC0)")]
        feats += prev
        errors.append(f"kept {len(prev)} Wikidata cases from the last build")
    old.write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False))
    counts = {}
    for f in feats:
        k = f"{f['properties']['group']} | {f['properties']['branch']}"
        counts[k] = counts.get(k, 0) + 1
    stamp.write_text(json.dumps({"read": datetime.date.today().isoformat(), "features": len(feats), "wikidata": len(wd), "lists": len(lists),
                                 "compiled": len(CASES), "by_tier_and_branch": dict(sorted(counts.items())), "found": found,
                                 "errors": errors}, indent=1, ensure_ascii=False))
    for e in errors:
        print("capture:", e, flush=True)
    print(f"capture: {len(feats)} cases ({len(wd)} from Wikidata)", flush=True)
    if not wd:
        sys.exit("capture: Wikidata gave nothing this time (the compiled cases were still written)")


if __name__ == "__main__":
    main()
