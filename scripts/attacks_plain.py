#!/usr/bin/env python3
"""
The attacks rows in plain English (round 119b, asked 30 September 2026).

The owner's collection Attacks On Activists was read into attacks/*.geojson
(round 110b). Those files keep each source's own words: the Land of
Resistance database in Spanish, the Indigenous Missionary Council (CIMI) and
the Pastoral Land Commission (CPT) in Portuguese, Front Line Defenders' saved
pages partly in Arabic, Russian and Turkish, Brazil's states as two-letter
codes, and the Land of Resistance's record dates as spreadsheet numbers. Here
each file is written again under attacks/plain/, with:

  - every short label (kinds of attack, what was defended, against what, the
    victims' occupations, Front Line Defenders' rights and violations tags) in
    English, from a table of the sources' own terms written for this map;
  - every longer text (descriptions, circumstances, what the defender did)
    machine-translated into English with Argos Translate (open-source, run
    here, nothing sent to any service), the original kept beside it as
    published; a text not yet translated keeps its original and says so. The
    translations are kept in attacks/plain/translations.json, so each day's
    run only translates what is new, within a time budget;
  - Brazil's two-letter state codes as the states' names (the code kept);
  - the Land of Resistance's record dates as dates ("added to the database on");
  - CIMI's cases with a family of violence (against land and property, against
    the person, by the state's neglect, against isolated peoples), from the
    report chapter each case was printed under, else from its kind;
  - the CPT's areas in land conflict drawn as their municipality's area
    (geoBoundaries' CGAZ municipal boundaries, from the owner's
    WelcomeToYourGalaxy/cgaz-boundaries copy), one shape per municipality and
    year, with the conflicts, families and hectares in it; rows that name only
    a state are drawn as the state.

Nothing is dropped: every record and every field of the source files is in
the new files.

Daily (it only translates what is new).
"""
import datetime, gzip, hashlib, json, math, os, pathlib, re, subprocess, sys, time, unicodedata, urllib.request

SRC = pathlib.Path("attacks")
OUT = SRC / "plain"
CACHE = OUT / "translations.json"
BUDGET = float(os.environ.get("ATTACKS_TRANSLATE_MINUTES", "110")) * 60
CGAZ = "https://raw.githubusercontent.com/WelcomeToYourGalaxy/cgaz-boundaries/main/"
UA = {"User-Agent": "Culprits atlas build (github.com/WelcomeToYourGalaxy)"}
LANG_NAME = {"pt": "Portuguese", "es": "Spanish", "ar": "Arabic", "ru": "Russian", "tr": "Turkish", "fr": "French"}

STATES = {"AC": "Acre", "AL": "Alagoas", "AP": "Amapá", "AM": "Amazonas", "BA": "Bahia", "CE": "Ceará", "DF": "Distrito Federal",
          "ES": "Espírito Santo", "GO": "Goiás", "MA": "Maranhão", "MT": "Mato Grosso", "MS": "Mato Grosso do Sul", "MG": "Minas Gerais",
          "PA": "Pará", "PB": "Paraíba", "PR": "Paraná", "PE": "Pernambuco", "PI": "Piauí", "RJ": "Rio de Janeiro", "RN": "Rio Grande do Norte",
          "RS": "Rio Grande do Sul", "RO": "Rondônia", "RR": "Roraima", "SC": "Santa Catarina", "SP": "São Paulo", "SE": "Sergipe", "TO": "Tocantins"}
COUNTRIES = {"BR": "Brazil", "HN": "Honduras", "CO": "Colombia", "MX": "Mexico", "GT": "Guatemala", "EC": "Ecuador", "PE": "Peru",
             "AR": "Argentina", "BO": "Bolivia", "PA": "Panama", "VE": "Venezuela", "CL": "Chile", "PY": "Paraguay", "NI": "Nicaragua",
             "SV": "El Salvador", "CR": "Costa Rica", "UY": "Uruguay"}

# The sources' own short terms, in English (written for this map; whole values only).
TERMS = {
    # Land of Resistance (Spanish)
    "persona": "Person", "organización": "Organisation", "comunidad": "Community", "hombre": "Man", "mujer": "Woman",
    "no aplica": "Does not apply", "sin información": "No information", "sin informacion": "No information", "lgbt": "LGBT",
    "sí": "Yes", "si": "Yes", "no": "No", "no autodeterminación": "Does not identify with an ethnic community",
    "not found": "Not found in the record", "varias etnias": "Several peoples", "afrodescendiente": "Afro-descendant",
    "tierra": "Land", "agua": "Water", "bosque": "Forest", "especies": "Species", "aire": "Air",
    "agroindustria": "Agribusiness", "minería": "Mining", "infraestructura": "Infrastructure", "forestal": "Forestry and plantations",
    "hidroeléctrica": "Hydroelectric dams", "tala": "Logging", "narcotráfico": "Drug trafficking", "hidrocarburos": "Oil and gas",
    "energía": "Energy", "pesquería": "Fishing industry", "especulación inmobiliaria": "Property speculation",
    "caza / tráfico biodiversidad": "Hunting and wildlife trafficking", "residuos": "Waste", "turismo": "Tourism",
    "amenaza": "Threat", "asesinato": "Killing", "acoso judicial": "Judicial harassment", "ataque directo": "Direct attack",
    "criminalización / estigmatización": "Criminalisation or stigmatisation", "otro": "Other", "desplazamiento": "Forced displacement",
    "desaparecido": "Disappeared", "violencia sexual": "Sexual violence", "sin investigación": "Not investigated",
    "investigación": "Under investigation", "sentencia": "Court ruling", "indulto": "Pardoned",
    "campesino": "Peasant farmer", "campesina": "Peasant farmer", "indígena": "Indigenous", "liderazgo indígena": "Indigenous leadership",
    "liderazgo": "Leadership", "agricultor": "Farmer", "pescador": "Fisher", "ama de casa": "Homemaker",
    "liderazgo afro_quilombolo": "Afro-descendant or quilombola leadership", "líder indígena": "Indigenous leader",
    "afro_quilombolo": "Afro-descendant or quilombola", "asentado": "Land-reform settler", "asentada": "Land-reform settler",
    "poseedor": "Land occupant (posseiro)", "sin tierra": "Landless worker", "ambientalista": "Environmentalist",
    "ribereño": "River-dweller", "ribereña": "River-dweller", "defensora": "Defender", "defensor": "Defender", "activista": "Activist",
    "líder afro": "Afro-descendant leader", "abogado": "Lawyer", "abogada": "Lawyer", "agente pastoral": "Pastoral agent",
    "no información": "No information", "no hay información": "No information", "extractivista": "Forest gatherer (extractivist)",
    "jornalero": "Day labourer", "docente": "Teacher", "comerciante": "Trader", "sacerdote": "Priest", "gobernador indígena": "Indigenous governor",
    "estudiante": "Student", "miembro": "Member", "integrante": "Member", "miembra": "Member", "presidente": "President", "presidenta": "President",
    "cacique indígena": "Indigenous chief", "cacique": "Chief", "gobernador": "Governor", "gobernadora": "Governor", "líder": "Leader",
    "representante legal": "Legal representative", "dirigente": "Leader", "coordinadora": "Coordinator", "coordinador": "Coordinator",
    "vocero": "Spokesperson", "vocera": "Spokesperson", "vicepresidente": "Vice-president", "fundador": "Founder", "fundadora": "Founder",
    "ex gobernador": "Former governor", "exgobernador": "Former governor", "vocal": "Board member", "directivo": "Board member",
    "directiva": "Board member", "expresidente": "Former president", "comunero": "Community member", "director": "Director",
    "secretario": "Secretary", "secretaria": "Secretary", "fiscal": "Auditor", "miembro directivo": "Board member",
    "coordinador general": "General coordinator", "guardaparques": "Park ranger", "miembro del movimiento": "Member of the movement",
    "reportería": "Own reporting", "prensa": "Press", "reportes periodísticos": "News reports",
    # CIMI and CPT (Portuguese)
    "liderança": "Leader", "sem - terra": "Landless worker", "sem-terra": "Landless worker", "posseiro": "Land occupant (posseiro)",
    "posseira": "Land occupant (posseiro)", "trab. rural": "Rural worker", "trabalhador rural": "Rural worker", "assentado": "Land-reform settler",
    "assentada": "Land-reform settler", "índio": "Indigenous person", "indígena (pt)": "Indigenous person", "ribeirinho": "River-dweller",
    "ribeirinha": "River-dweller", "presidente de str": "President of a rural workers' union", "ag. pastoral": "Pastoral agent",
    "agente pastoral (pt)": "Pastoral agent", "religioso": "Member of the clergy", "religiosa": "Member of the clergy",
    "dirigente sindical": "Union leader", "quilombola": "Quilombola (Afro-Brazilian community)", "aliados": "Ally", "pescador (pt)": "Fisher",
    "sindicalista": "Trade unionist", "liderança indígena": "Indigenous leader", "funcionário público": "Public servant",
    "político": "Politician", "pequeno proprietário": "Smallholder", "faxinalense": "Faxinalense (traditional communal-land community)",
    "advogado": "Lawyer", "ameaçados de morte": "Threatened with death", "ameaça de morte": "Threatened with death",
    "ameaçado de morte": "Threatened with death", "tentativas de assassinato": "Attempted murder", "assassinatos": "Murder",
    "ameaçados de prisão": "Threatened with arrest", "tentativa/ameaça exp.": "Attempted or threatened eviction",
    "perseguição política": "Political persecution", "despejos": "Evictions", "ameaça de despejo": "Threat of eviction",
    "pistolagem": "Hired gunmen", "trabalho escravo": "Slave labour", "expulsão": "Expulsion",
    "conflito em área indígena": "Conflict on Indigenous land", "conflitos pela água": "Water conflict",
    "repressão à manifestação": "Repression of a protest", "ausência de políticas públicas": "No public policy",
    "sem informação": "No information", "questão ambiental": "Environmental dispute", "manifestação": "Protest", "invasão": "Invasion",
    "conflito trabalhista": "Labour dispute", "grilagem": "Land grabbing with forged titles (grilagem)",
    "falhas da política de assentamento": "Failures of land-reform settlement policy", "superexploração": "Overexploitation of workers",
    "conflitos em área de garimpo": "Conflict in a wildcat-mining area", "destruição de roças": "Destruction of crops",
    "assentamento inadequado": "Inadequate settlement", "desrespeito trabalhista": "Labour rights violated",
    "conflito em área quilombola": "Conflict on quilombola land", "uso e preservação": "Use and preservation",
    "barragens e açudes": "Dams and reservoirs", "apropriação particular": "Private appropriation", "açudes": "Reservoirs",
    "cobrança": "Charging for water", "destruição e ou poluição": "Destruction or pollution",
    "não cumprimento de procedimentos legais": "Legal procedures not followed", "procedimentos legais": "Legal procedures not followed",
    "diminuição do acesso à água": "Less access to water", "ameaça de expropriação": "Threat of expropriation",
    "impedimento de acesso à água": "Access to water blocked", "desconstrução do histórico-cultural": "Destruction of history and culture",
    "não reassentamento": "Not resettled", "pesca predatória": "Predatory fishing", "falta de projeto de reassentamento": "No resettlement plan",
    "reassentamento inadequado": "Inadequate resettlement", "contaminação por agrotóxico": "Pesticide contamination",
    "divergência": "Dispute", "expropriação": "Expropriation",
    "assasinatos, violência contra a pessoa": "Murder; violence against the person",
    "assassinatos, violência contra a pessoa": "Murder; violence against the person",
}
# Front Line Defenders' own tags in the languages of the saved pages, as its English pages word them.
FLD_TAGS = {
    "حقوق الإنسان": "Human Rights", "الفَسَاد": "Corruption", "الحُقُوقُ البِيئيّة": "Environmental Rights",
    "الحُقُوق المدنيّة والسّياسيّة": "Civil & Political Rights", "свобода выражения мнений": "Freedom of Expression",
    "حَقُّ الأرض": "Land Rights", "حُرِّيةُ التَّعبِير": "Freedom of Expression", "земельные права": "Land Rights",
    "حُقُوقُ العُمّال": "Labour Rights / Trade Union", "حُرِّيةُ التّجمُّع وتَكوِين الجَمعيّات": "Freedom of Association",
    "гражданские и политические права": "Civil & Political Rights", "права коренных народностей": "Indigenous Peoples / Campesino Rights",
    "права детей": "Children's Rights", "права человека": "Human Rights", "свобода объединений": "Freedom of Association",
    "трудовые права": "Labour Rights / Trade Union", "مشاركة المواطن": "Citizen Participation", "حقوق مجتمع المثليين": "LGBT+ Rights",
    "беженцы / внутренне перемещенные лица / мигранты": "Refugees / IDPs / Migrants", "экологические права": "Environmental Rights",
    "права женщин и гендерные права": "Gender/Women's Rights", "الجِنسَانيّة وحُقُوق المَرأةُ": "Gender/Women's Rights",
    "تَقرِيرُ المَصِير": "Self-Determination", "حُقُوقُ الشُّعوب الَأصلِيَّة": "Indigenous Peoples / Campesino Rights",
    "حُقُوقُ الأقلِّيات": "Minority Rights", "النّشاطُ السّيبراني": "Cyber Activism", "الصّحافَةُ": "Journalism",
    "حقوق السجناء و السجينات": "Prisoner Rights", "الإِفلات مِن العِقاب / العَدَالَة": "Impunity / Justice", "права лгбти": "LGBT+ Rights",
    "протесты / собрания": "Protests / Assembly", "права заключенных": "Prisoner Rights", "доступ к услугам здравоохранения": "Access to Healthcare",
    "المُضايَقةُ القَضَائِيَّة": "Judicial Harassment", "арест/задержание/тюремное заключение": "Arrest / Detention / Imprisonment",
    "الاعتِقالُ / التَّوقِيفُ / السِّجنُ": "Arrest / Detention / Imprisonment", "الاحتِجازُ التَّعسُفيّ": "Arbitrary detention",
    "судебное преследование": "Judicial Harassment", "المُداهَمَةُ / الاقتِحَامُ / السَّرقَةُ": "Raid / Break-in / Theft",
    "i̇zleme": "Surveillance", "izleme": "Surveillance", "угрозы/запугивание": "Threats / Intimidation", "yargısal taciz": "Judicial Harassment",
    "الاستِجوَابُ / التَّحقِيقُ": "Questioning / Interrogation", "الأعمال الإنتقامية": "Reprisals", "расправа": "Reprisals",
    "произвольное задержание": "Arbitrary detention", "diğer tacizler": "Other Harassment", "حَظرُ السَّفَر": "Travel Ban",
    "مُحاوَلةُ القَتلِ": "Attempted Killing", "التَّهدِيد / التَّخويِف": "Threats / Intimidation", "облава/взлом/кража": "Raid / Break-in / Theft",
    "нападение": "Physical Attack", "yakalama / gözaltı / hapis": "Arrest / Detention / Imprisonment", "عنف": "Violence",
    "الاختِفَاءُ القَسرِيّ": "Enforced Disappearance", "التَّعذِيب / سُوءُ المُعَامَلَة": "Torture / Ill-Treatment",
    "مُضايَقات أُخرَى": "Other Harassment", "الاعتِداءُ الجَسَدِي": "Physical Attack", "المُراقَبَةُ": "Surveillance", "التشهير": "Defamation",
    "حَمَلاتُ التَّشهِير": "Smear Campaign", "запрет на выезд": "Travel Ban", "насилие": "Violence", "пытки/дурное обращение": "Torture / Ill-Treatment",
    "убийство": "Killing", "misilleme": "Reprisals", "seyahat yasağı": "Travel Ban", "keyfi gözaltı": "Arbitrary detention",
    "karalama kampanyası": "Smear Campaign", "siber-saldırı": "Cyber-attack", "sorgulama": "Questioning / Interrogation",
    "fiziksel saldırı": "Physical Attack", "يواجه اتهامات": "Facing charges", "متهم": "Charged", "حظر السّفر": "Travel Ban",
}
# Group names that carried the sources' own words or our shorthand.
GROUP_WORDS = {
    "Massacre (CPT: 3 or more killed in one land-conflict event)": "Massacre: three or more people killed in one land conflict (the Pastoral Land Commission's definition)",
    'Killing (source: "Assasinatos, Violência contra a pessoa")': "Killing",
    "Other: Açudes": "Other: reservoirs", "Other: Sem Informação": "Other: no information", "Other: Cobrança": "Other: charging for water",
    "Type not read (columns not verified)": "Kind not read from the table",
    "Other (section: Povos indígenas continuam sendo exterminados na Amazônia)": "Other (section: Indigenous peoples are still being exterminated in the Amazon)",
}
CIMI_FAMILY = [
    ("Against isolated and recently contacted peoples", r"isolad|pouco contato|isolated|recently contacted"),
    ("By the state's neglect: health, schooling, help", r"omiss|desassist|sa[uú]de|suic|mortalidade|educa|lack of|neglect|malnutrition|suicide|child mortality|child deaths|alcohol"),
    ("Against their land and property", r"patrim|territor|regulariza|invas|land regularisation|territorial|invasion|property|environmental and biological|farming"),
    ("Against the person: killings, attacks, threats", r"pessoa|assassin|les[õo]es|tentativ|racismo|amea[çc]a|sexual|abuso|murder|manslaughter|threat|bodily|abuse of power|racism|disappearance|misappropriation"),
]
TEXT_FIELDS = {
    "land_of_resistance": ("es", ["defence_activity", "event_description", "violence_context", "other_types_of_violence", "conflict_other_place", "event_other_place"]),
    "cimi_indigenous_violence": ("pt", ["description", "means_used", "type_of_damage_or_conflict", "circumstances", "motive_or_means_used", "measures_taken",
                                        "causes_and_circumstances", "consequences", "type_of_conflict", "type_of_conflict_and_parties", "type_of_damage",
                                        "type_of_activity", "situation", "section (as printed)", "chapter"]),
    "caci_indigenous": ("pt", ["description"]),
    "cpt_massacres": ("pt", ["description (Portuguese, as published)"]),
    "frontline_cases": (None, ["title", "status", "about the situation", "about the defender", "role", "case updates"]),
}
LABEL_FIELDS = {
    "land_of_resistance": ("es", ["name_type", "gender", "ethnic_community (yes/no)", "ethnic_community", "resource_defended", "defending_from",
                                  "type_of_violence", "case_status", "state_responsibility", "complaints_or_alerts_to_state", "occupation", "position",
                                  "information_source"]),
    "caci_indigenous": ("pt", ["types_of_violence"]),
    "cpt_violence_tables": ("pt", ["category"]),
    "cpt_threatened_2000_2011": ("pt", ["category", "type_of_violence", "situation_of_violence", "sheet title"]),
    "cpt_water_conflicts": ("pt", ["conflict_type", "conflict_situation"]),
}
# The smaller files first, so their English is made on the first run; CIMI's
# 9,202 cases last (they take several days' runs to translate).
FILES = ["gw_killings", "cpt_massacres", "caci_indigenous", "frontline_cases", "cpt_violence_tables", "cpt_threatened_2000_2011",
         "cpt_water_conflicts", "cpt_overexploitation", "cpt_slave_labour_cases", "cpt_slave_labour_by_state", "public_agencies_conflicts",
         "cpt_areas_of_conflict", "cpt_land_conflicts", "land_of_resistance", "cimi_indigenous_violence"]


def plain(s):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower().replace("'", "").replace("-", " ")).strip()


class Translator:
    """Argos Translate, run on the build machine; every result kept in CACHE."""

    def __init__(self):
        self.cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
        self.started = time.time()
        self.ready = {}
        self.new = 0
        self.pending = 0
        self.failed = None
        self.argos = None

    def _load(self, lang):
        if lang in self.ready:
            return self.ready[lang]
        self.ready[lang] = None
        try:
            if self.argos is None:
                subprocess.run([sys.executable, "-m", "pip", "install", "-q", "argostranslate"], check=True)
                import argostranslate.package, argostranslate.translate   # noqa: E401
                argostranslate.package.update_package_index()
                self.argos = (argostranslate.package, argostranslate.translate)
            pkg, tr = self.argos
            have = {(p.from_code, p.to_code) for p in pkg.get_installed_packages()}
            if (lang, "en") not in have:
                want = next(p for p in pkg.get_available_packages() if p.from_code == lang and p.to_code == "en")
                pkg.install_from_path(want.download())
            self.ready[lang] = lambda text: tr.translate(text, lang, "en")
        except Exception as e:  # noqa: BLE001
            self.failed = f"{lang}: {type(e).__name__}: {e}"
            print(f"attacks_plain: no translation from {lang} ({e})", flush=True)
        return self.ready[lang]

    def __call__(self, text, lang):
        text = str(text or "").strip()
        if not text or not lang or lang == "en":
            return None
        key = hashlib.sha1(f"{lang}|{text}".encode("utf-8")).hexdigest()
        if key in self.cache:
            return self.cache[key]
        if time.time() - self.started > BUDGET:
            self.pending += 1
            return None
        fn = self._load(lang)
        if not fn:
            self.pending += 1
            return None
        try:
            out = fn(text)
        except Exception as e:  # noqa: BLE001
            print(f"attacks_plain: a text from {lang} could not be translated ({e})", flush=True)
            self.pending += 1
            return None
        self.cache[key] = out
        self.new += 1
        if self.new % 200 == 0:
            self.save()
            print(f"attacks_plain: {self.new} new translations", flush=True)
        return out

    def save(self):
        OUT.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(self.cache, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


DICT_ONLY = {"information_source", "ethnic_community", "ethnic_community (yes/no)", "gender", "name_type"}


def label(v, lang, mt, field=""):
    s = str(v).strip()
    hit = TERMS.get(s.lower())
    if hit:
        return hit
    if field in DICT_ONLY:
        return None
    if len(s) <= 120:
        return mt(s, lang)
    return None


def excel_date(v):
    try:
        d = datetime.datetime(1899, 12, 30) + datetime.timedelta(days=float(v))
        return d.strftime("%Y-%m-%d")
    except Exception:  # noqa: BLE001
        return None


def tagkey(t):
    t = unicodedata.normalize("NFC", str(t)).lower()
    return re.sub(r"[\u064b-\u0652\u0670\u0640]", "", t).strip()


FLD_INDEX = {tagkey(k): v for k, v in FLD_TAGS.items()}


def fld_tags(v):
    out, unknown = [], []
    vals = v if isinstance(v, list) else [v]
    for item in vals:
        for t in re.split(r"\s*#", str(item or "")):
            t = t.strip()
            if not t:
                continue
            en = FLD_INDEX.get(tagkey(t))
            if en:
                out.append(en)
            elif re.fullmatch(r"[\x00-\x7f]+", t):
                out.append(t)
            else:
                out.append(t)
                unknown.append(t)
    return list(dict.fromkeys(out)), unknown


def tidy(name, feats, mt, report):
    lang_text, text_fields = TEXT_FIELDS.get(name, (None, []))
    lang_label, label_fields = LABEL_FIELDS.get(name, (None, []))
    for f in feats:
        p = f["properties"]
        new = {}
        lang = lang_text
        if name == "frontline_cases":
            m = re.match(r"https?://[^/]+/([a-z]{2})/", str(p.get("url") or ""))
            lang = m.group(1) if m else "en"
        for k, v in p.items():
            if v is None or v == "":
                new[k] = v
                continue
            # Brazil's states by name, the code kept.
            if k in ("state", "state (from heading)", "state_code") and isinstance(v, str) and v.upper() in STATES and name.startswith(("cpt_", "cimi", "public_")):
                new[k] = STATES[v.upper()]
                new[f"{k} (code)"] = v
                continue
            if name == "land_of_resistance" and k == "record_created_at (Excel serial date, as given)":
                new["added to the database on"] = excel_date(v) or v
                continue
            if name == "land_of_resistance" and k == "country_code":
                new["country"] = COUNTRIES.get(str(v).upper(), v)
                new["country code"] = v
                continue
            if name == "frontline_cases" and k in ("rights", "violations"):
                en, unknown = fld_tags(v)
                new[k] = "; ".join(en)
                if v != en:
                    new[f"{k} (as tagged on the page)"] = v if isinstance(v, str) else "; ".join(map(str, v))
                for u in unknown:
                    report["frontline tags not in the table"][u] = report["frontline tags not in the table"].get(u, 0) + 1
                continue
            if k in label_fields and isinstance(v, str):
                en = label(v, lang_label, mt, k)
                if en and en != v:
                    new[k] = en
                    new[f"{k} (as given, {LANG_NAME.get(lang_label, lang_label)})"] = v
                else:
                    new[k] = v
                continue
            if k in text_fields and isinstance(v, (str, list)) and lang and lang != "en":
                text = v if isinstance(v, str) else "; ".join(map(str, v))
                if k == "description (Portuguese, as published)":
                    en = mt(text, lang)
                    new["description"] = en if en else "(English translation not made yet: the Portuguese is below)"
                    new[k] = v
                    continue
                en = mt(text, lang) if len(text) > 120 or not TERMS.get(text.lower()) else TERMS.get(text.lower())
                if en:
                    new[k] = en
                    new[f"{k} (as published, {LANG_NAME.get(lang, lang)})"] = v
                else:
                    new[k] = v
                    new[f"{k}: English"] = "not made yet"
                continue
            new[k] = v
        if new.get("group") in GROUP_WORDS:
            new["group (as first read)"] = new["group"]
            new["group"] = GROUP_WORDS[new["group"]]
        if name == "cimi_indigenous_violence":
            basis = f"{p.get('chapter') or ''} {p.get('section (as printed)') or ''}"
            # Delay in recognising land is printed under Chapter I, violence
            # against land and property, though its words say "omission".
            fam = "Against their land and property" if re.search(r"regulariza", plain(basis) + " " + str(p.get("group") or "").lower()) else None
            fam = fam or next((t for t, rx in CIMI_FAMILY if re.search(rx, plain(basis))), None)
            if not fam:
                fam = next((t for t, rx in CIMI_FAMILY if re.search(rx, str(p.get("group") or "").lower())), "Other")
            new["family of violence"] = fam
        if name == "frontline_cases" and lang != "en":
            new["language of the saved page"] = LANG_NAME.get(lang, lang)
        f["properties"] = new
    return feats


# ---- the CPT's areas in conflict as municipal shapes ---------------------------
def ring_bbox(ring):
    xs = [c[0] for c in ring]
    ys = [c[1] for c in ring]
    return min(xs), min(ys), max(xs), max(ys)


def inside(pt, poly):
    x, y = pt
    hit = False
    for ring in poly:
        n = len(ring)
        j = n - 1
        for i in range(n):
            xi, yi = ring[i][0], ring[i][1]
            xj, yj = ring[j][0], ring[j][1]
            if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi:
                hit = not hit
            j = i
    return hit


def polys(geom):
    return [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]


def simplify(ring, tol):
    """Douglas-Peucker, keeping the ring closed and at least four points."""
    if len(ring) < 8:
        return ring
    keep = [False] * len(ring)
    keep[0] = keep[-1] = True
    # A closed ring starts and ends on one point: split it first at the point
    # farthest from there.
    far_i = max(range(len(ring)), key=lambda i: math.hypot(ring[i][0] - ring[0][0], ring[i][1] - ring[0][1]))
    keep[far_i] = True
    stack = [(0, far_i), (far_i, len(ring) - 1)]
    while stack:
        a, b = stack.pop()
        ax, ay = ring[a][0], ring[a][1]
        bx, by = ring[b][0], ring[b][1]
        dx, dy = bx - ax, by - ay
        L = math.hypot(dx, dy) or 1e-12
        far, at = 0.0, None
        for i in range(a + 1, b):
            d = abs(dy * ring[i][0] - dx * ring[i][1] + bx * ay - by * ax) / L
            if d > far:
                far, at = d, i
        if at is not None and far > tol:
            keep[at] = True
            stack += [(a, at), (at, b)]
    out = [c for c, k in zip(ring, keep) if k]
    return out if len(out) >= 4 else ring


def rounded(geom, d=4, tol=0.006):
    """Coordinates to four places, outlines simplified to about 600 m: the
    shape is for shading the municipality, not for its exact border."""
    def r(ring):
        return [[round(c[0], d), round(c[1], d)] for c in simplify(ring, tol)]
    if geom["type"] == "Polygon":
        return {"type": "Polygon", "coordinates": [r(ring) for ring in geom["coordinates"]]}
    return {"type": "MultiPolygon", "coordinates": [[r(ring) for ring in poly] for poly in geom["coordinates"]]}


def get_json(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=300) as r:
        return json.loads(r.read())


def number(v):
    m = re.search(r"[\d.,]+", str(v or ""))
    if not m:
        return None
    s = m.group(0)
    # Brazilian tables write thousands with a dot.
    s = s.replace(".", "").replace(",", ".") if re.fullmatch(r"\d{1,3}(\.\d{3})+(,\d+)?", s) or "," in s else s
    try:
        return float(s)
    except ValueError:
        return None


def municipal_areas(feats, report):
    muni = get_json(CGAZ + "BRA2.geojson")["features"]
    states = get_json(CGAZ + "BRA.geojson")["features"]
    by_name = {}
    for i, m in enumerate(muni):
        by_name.setdefault(plain(m["properties"].get("shapeName")), []).append(i)
        m["_bb"] = [ring_bbox(poly[0]) for poly in polys(m["geometry"])]
    state_shape = {plain(s["properties"].get("shapeName")): s for s in states}

    def contains(i, pt):
        for bb, poly in zip(muni[i]["_bb"], polys(muni[i]["geometry"])):
            if bb[0] <= pt[0] <= bb[2] and bb[1] <= pt[1] <= bb[3] and inside(pt, poly):
                return True
        return False

    def nearest(cands, pt):
        best, bd = None, 1e9
        for i in cands:
            for bb in muni[i]["_bb"]:
                cx, cy = (bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2
                d = math.hypot(cx - pt[0], cy - pt[1])
                if d < bd:
                    best, bd = i, d
        return best, bd

    groups, how = {}, {"by name and position": 0, "by name, nearest of its namesakes": 0, "by position only": 0, "state only": 0, "not placed": 0}
    for f in feats:
        p = f["properties"]
        pt = (f.get("geometry") or {}).get("coordinates")
        town = p.get("municipality")
        year = p.get("year")
        state_name = p.get("state") or ""
        key = None
        if town:
            cands = by_name.get(plain(town), [])
            inner = [i for i in cands if pt and contains(i, pt)]
            if inner:
                key, how_ = ("m", inner[0]), "by name and position"
            elif cands and pt:
                i, d = nearest(cands, pt)
                if d < 3:
                    key, how_ = ("m", i), "by name, nearest of its namesakes"
            if key is None and pt:
                bbox_hits = [i for i in range(len(muni)) if contains(i, pt)] if not cands else []
                if bbox_hits:
                    key, how_ = ("m", bbox_hits[0]), "by position only"
        if key is None:
            s = state_shape.get(plain(state_name))
            if s is not None:
                key, how_ = ("s", plain(state_name)), "state only"
            else:
                how["not placed"] += 1
                report["areas not placed"].append(p.get("name"))
                continue
        how[how_] += 1
        g = groups.setdefault((key, year), {"rows": [], "how": set()})
        g["rows"].append(p)
        g["how"].add(how_)
    out = []
    for (key, year), g in groups.items():
        rows = g["rows"]
        if key[0] == "m":
            shape = muni[key[1]]
            town = shape["properties"].get("shapeName")
        else:
            shape = state_shape[key[1]]
            town = None
        state = rows[0].get("state") or ""
        fam = [number(r.get("families")) for r in rows]
        ha = [number(r.get("area")) for r in rows]
        listed = []
        for r in rows:
            bits = [str(r.get("conflict_name") or r.get("name") or "")]
            if r.get("families"):
                bits.append(f"{r['families']} families")
            if r.get("area"):
                bits.append(f"{r['area']} ha")
            listed.append(", ".join(b for b in bits if b))
        props = {
            "name": f"{town}, {state}" if town else f"{state} (no town named)",
            "municipality": town or "", "state": state, "year": year,
            "areas in conflict": len(rows),
            "families (sum of the figures given)": int(sum(x for x in fam if x)) if any(fam) else None,
            "hectares (sum of the figures given)": round(sum(x for x in ha if x), 1) if any(ha) else None,
            "areas in conflict, listed": "; ".join(listed),
            "drawn as": ("the municipality's area (geoBoundaries CGAZ), matched " + " and ".join(sorted(g["how"]))) if town
                        else "the whole state: these rows name no town",
            "rows match the printed state subtotals": "; ".join(sorted({str(r.get("check against printed subtotal")) for r in rows if r.get("check against printed subtotal")}))[:600],
            "group": "Areas in conflict in a municipality" if town else "Areas in conflict in a state, no town named",
            "source": "Comissão Pastoral da Terra (CPT), Conflitos no Campo, Áreas em Conflito, read from its yearly tables; municipal boundaries geoBoundaries CGAZ (CC BY 4.0)",
        }
        out.append({"type": "Feature", "geometry": rounded(shape["geometry"]), "properties": props})
    out.sort(key=lambda f: (str(f["properties"]["year"]), f["properties"]["name"]))
    report["areas matched"] = how
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    mt = Translator()
    report = {"built": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "files": {}, "frontline tags not in the table": {}, "areas not placed": []}
    areas_src = None
    for name in FILES:
        src = SRC / f"{name}.geojson"
        if not src.exists():
            report["files"][name] = "not there"
            continue
        d = json.loads(src.read_text(encoding="utf-8"))
        feats = d.get("features") or []
        n = len(feats)
        if name == "cpt_areas_of_conflict":
            areas_src = json.loads(json.dumps(feats))
        tidy(name, feats, mt, report)
        d["features"] = feats
        (OUT / f"{name}.geojson").write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        report["files"][name] = n
        print(f"attacks_plain: {name}: {n} records", flush=True)
    mt.save()
    if areas_src:
        tidy("cpt_areas_of_conflict", areas_src, mt, report)
        try:
            shapes = municipal_areas(areas_src, report)
            (OUT / "cpt_areas_municipal.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": shapes}, ensure_ascii=False,
                                                                       separators=(",", ":")), encoding="utf-8")
            report["files"]["cpt_areas_municipal"] = len(shapes)
            print(f"attacks_plain: areas in conflict as {len(shapes)} municipal shapes", flush=True)
        except Exception as e:  # noqa: BLE001
            report["areas"] = f"not drawn as shapes: {type(e).__name__}: {e}"
            print(f"attacks_plain: areas as shapes failed ({e})", flush=True)
    report["translations"] = {"kept": len(mt.cache), "made this run": mt.new, "not made yet (time budget or no model)": mt.pending,
                              "engine": "Argos Translate (open-source, run on the build machine)", "trouble": mt.failed}
    (OUT / "build.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"attacks_plain: {mt.new} translated this run, {mt.pending} left for later runs", flush=True)


if __name__ == "__main__":
    main()
