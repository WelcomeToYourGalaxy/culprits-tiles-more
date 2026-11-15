"""Non-renewable groundwater drained per kilo of crop, by country, 26 crop classes,
2000 and 2010: Supplementary Table 1 of

  Dalin, C., Wada, Y., Kastner, T. & Puma, M. J. Groundwater depletion embedded in
  international food trade. Nature 543, 700-704 (2017).
  https://doi.org/10.1038/nature21403

Used for non-commercial purposes with the citation and DOI, by permission of Dr
Carole Dalin (email, November 2026). The table is fixed, so this runs only when
water/groundwater_crops.json is missing.

Written by ISO3. Every crop's two figures are kept, in the table's own terms:
"no pumping data" is its NGD, "no production data" its NPD, and a zero it prints
in bold is a zero reported for groundwater pumping. x_highest_2010 is the largest
figure among the country's crop classes in 2010: what the map shades. Countries
the table lists under a name with no outline today (Czechoslovakia, Yugoslav SFR,
Ethiopia PDR, Netherlands Antilles, Serbia and Montenegro) are kept under "_other".
Belgium-Luxembourg is written to both.
"""
import io, json, pathlib, sys, urllib.request

URL = "https://static-content.springer.com/esm/art%3A10.1038%2Fnature21403/MediaObjects/41586_2017_BFnature21403_MOESM249_ESM.xlsx"
OUT = pathlib.Path("water/groundwater_crops.json")
CITE = "Dalin, Wada, Kastner and Puma (2017), Groundwater depletion embedded in international food trade, Nature 543, 700-704, https://doi.org/10.1038/nature21403"
ISO = dict(Armenia="ARM", Afghanistan="AFG", Albania="ALB", Algeria="DZA", Angola="AGO", Argentina="ARG", Australia="AUS", Austria="AUT", Bahamas="BHS", Bahrain="BHR", Barbados="BRB", Bangladesh="BGD", Bermuda="BMU", Bhutan="BTN", Bolivia="BOL", Botswana="BWA", Brazil="BRA", Aruba="ABW", Belize="BLZ", Bruneidarussalam="BRN", Bulgaria="BGR", Myanmar="MMR", Burundi="BDI", Cameroon="CMR", Canada="CAN", Capeverde="CPV", Caymanislands="CYM", CentralAfricanRepublic="CAF", SriLanka="LKA", Chad="TCD", Chile="CHL", Colombia="COL", Congo="COG", Cookislands="COK", Costarica="CRI", Cuba="CUB", Cyprus="CYP", Azerbaijan="AZE", Benin="BEN", Denmark="DNK", DominicanRepublic="DOM", Belarus="BLR", Ecuador="ECU", Egypt="EGY", ElSalvador="SLV", EquatorialGuinea="GNQ", Estonia="EST", faroeislands="FRO", Fiji="FJI", Finland="FIN", France="FRA", frenchguiana="GUF", frenchpolynesia="PYF", Djibouti="DJI", Georgia="GEO", Gabon="GAB", Gambia="GMB", Germany="DEU", BosniaandHerzegovina="BIH", Ghana="GHA", Kiribati="KIR", Greece="GRC", Grenada="GRD", Guadeloupe="GLP", Guatemala="GTM", Guinea="GIN", Guyana="GUY", Haiti="HTI", Honduras="HND", Hungary="HUN", Croatia="HRV", Iceland="ISL", India="IND", Indonesia="IDN", Iran="IRN", Iraq="IRQ", Ireland="IRL", Israel="ISR", Italy="ITA", CotedIvoire="CIV", Kazakhstan="KAZ", Jamaica="JAM", Japan="JPN", Jordan="JOR", Kyrgyzstan="KGZ", Kenya="KEN", Cambodia="KHM", RepublicofKorea="KOR", Kuwait="KWT", Latvia="LVA", Laos="LAO", Lebanon="LBN", Lesotho="LSO", Liberia="LBR", Libya="LBY", Lithuania="LTU", Madagascar="MDG", Malawi="MWI", Malaysia="MYS", Maldives="MDV", Mali="MLI", Malta="MLT", Martinique="MTQ", Mauritania="MRT", Mauritius="MUS", Mexico="MEX", Mongolia="MNG", Morocco="MAR", Mozambique="MOZ", Moldova="MDA", Namibia="NAM", Nepal="NPL", Netherlands="NLD", NewCaledonia="NCL", Macedonia="MKD", NewZealand="NZL", Nicaragua="NIC", Niger="NER", Nigeria="NGA", Norway="NOR", Pakistan="PAK", Panama="PAN", CzechRepublic="CZE", PapuaNewGuinea="PNG", Paraguay="PRY", Peru="PER", Philippines="PHL", Poland="POL", Portugal="PRT", GuineaBissau="GNB", Timorleste="TLS", PuertoRico="PRI", Eritrea="ERI", Qatar="QAT", Zimbabwe="ZWE", Reunion="REU", Romania="ROU", Rwanda="RWA", Russia="RUS", saintlucia="LCA", SaudiArabia="SAU", Senegal="SEN", Seychelles="SYC", SierraLeone="SLE", Slovenia="SVN", Slovakia="SVK", Singapore="SGP", Somalia="SOM", SouthAfrica="ZAF", Spain="ESP", WesternSahara="ESH", Sudan="SDN", Suriname="SUR", Tajikistan="TJK", Swaziland="SWZ", Sweden="SWE", Switzerland="CHE", Syria="SYR", Turkmenistan="TKM", Tanzania="TZA", Thailand="THA", Togo="TGO", trinidadandtobago="TTO", Oman="OMN", Tunisia="TUN", Turkey="TUR", UAE="ARE", Uganda="UGA", UK="GBR", Ukraine="UKR", USA="USA", BurkinaFaso="BFA", Uruguay="URY", Uzbekistan="UZB", Venezuela="VEN", Vietnam="VNM", Samoa="WSM", Yemen="YEM", DRCongo="COD", Zambia="ZMB", China="CHN")
ISO["DPR Korea"] = "PRK"
PRETTY = {"BelgiumLuxembourg": "Belgium-Luxembourg", "Czechoslovakia": "Czechoslovakia", "Yugoslavsfr": "Yugoslav SFR", "NetherlandsAntilles": "Netherlands Antilles", "Serbiaandmontenegro": "Serbia and Montenegro"}
WORD = {"NGD": "no pumping data", "NPD": "no production data"}


def cell(c):
    if isinstance(c.value, str):
        return WORD.get(c.value.strip(), c.value.strip())
    if c.value == 0 and c.font and c.font.b:
        return "0 (zero pumping reported)"
    return f"{c.value:g} L/kg" if c.value else "0"


def build(xlsx):
    import openpyxl
    s = openpyxl.load_workbook(io.BytesIO(xlsx)).active
    assert "2000" in s.cell(1, 1).value and "2010" in s.cell(34, 1).value
    out, other = {}, {}
    for col in range(4, s.max_column + 1):
        raw, fao = s.cell(2, col).value, s.cell(1, col).value
        assert raw == s.cell(35, col).value
        d, best, crop = {"x_Country": PRETTY.get(raw, raw)}, None, None
        for k in range(26):
            a, b = s.cell(3 + k, col), s.cell(36 + k, col)
            name = s.cell(3 + k, 1).value
            assert name == s.cell(36 + k, 1).value
            d[f"x_{name}"] = f"2000: {cell(a)}; 2010: {cell(b)}"
            if isinstance(b.value, (int, float)) and (best is None or b.value > best):
                best, crop = b.value, name
        if best is None:
            d["x_note"] = "The table gives no figure for 2010"
        else:
            d["x_highest_2010"], d["x_highest_crop_2010"] = best, crop
        d["x_source"] = CITE
        if raw == "Ethiopia":                    # FAO 62 is Ethiopia PDR; 238 is today's Ethiopia
            (other if fao == 62 else out).update({"Ethiopia PDR": d} if fao == 62 else {"ETH": d})
        elif raw == "BelgiumLuxembourg":
            out["BEL"] = out["LUX"] = d
        elif raw in ISO:
            out[ISO[raw]] = d
        else:
            other[PRETTY.get(raw, raw)] = d
    out["_other"] = other
    return out


def main():
    if OUT.exists():
        print("groundwater_crops: the table is fixed and already copied")
        return
    try:
        req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0 (Culprits atlas build)"})
        data = build(urllib.request.urlopen(req, timeout=120).read())
    except Exception as e:  # noqa: BLE001
        sys.exit(f"groundwater_crops: {e}")
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=0))
    print(f"groundwater_crops: {len(data) - 1} countries, {len(data['_other'])} under other names")


if __name__ == "__main__":
    main()
