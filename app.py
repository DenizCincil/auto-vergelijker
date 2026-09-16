# app.py

import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
import pandas as pd
from urllib.parse import urlparse

st.set_page_config(page_title="Auto Vergelijker", page_icon="🚗", layout="wide")
st.title("🚗 Auto Vergelijker")
st.caption("Plak maximaal 3 advertentie-links om auto's te vergelijken.")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "nl-NL,nl;q=0.9,en;q=0.8",
}

COLOR_NL = {
    "black": "Zwart", "white": "Wit", "grey": "Grijs", "gray": "Grijs",
    "silver": "Zilver", "blue": "Blauw", "red": "Rood", "green": "Groen",
    "orange": "Oranje", "yellow": "Geel", "brown": "Bruin", "beige": "Beige",
}

BEKENDE_OPTIES = {
    "trekhaak", "panorama", "schuifdak", "amg", "dakrailing", "dakreling",
    "multibeam", "led koplamp", "stoelverwarming", "verwarmde", "elektrisch verstelbare",
    "sfeerverlichting", "navigati", "mbux", "head-up", "carplay", "android auto",
    "cruise control", "tempomat", "snelheidsregelaar", "smartphone integratie",
}

def nl_color(c):
    return COLOR_NL.get(c.lower(), c.capitalize())

def find_color(text):
    colors = ["zwart", "wit", "grijs", "zilver", "blauw", "rood", "groen",
              "oranje", "geel", "bruin", "beige", "black", "white", "grey",
              "gray", "silver", "blue", "red", "green"]
    for c in colors:
        if re.search(rf"\b{c}\b", text, re.IGNORECASE):
            return nl_color(c)
    return "?"

def heeft_optie(text, *patterns):
    for p in patterns:
        if re.search(p, text, re.IGNORECASE):
            return "Ja"
    return "Nee"

def re_val(pattern, text, group=1, default="?"):
    m = re.search(pattern, text, re.IGNORECASE)
    return m.group(group).strip() if m else default


# ─────────────────────────────────────────────
# DYNAMISCHE OPTIES EXTRACTOR
# Geeft een SET terug (voor vergelijking)
# ─────────────────────────────────────────────
def extract_extra_opties(soup, full_text):
    gevonden = set()

    # Methode 1: <li> items
    for li in soup.find_all("li"):
        tekst = li.get_text(" ", strip=True)
        tekst = re.sub(r"^\*?\*?[A-Z0-9]{2,4}\*?\*?\s*[-–]\s*", "", tekst)
        tekst = re.sub(r"^\d+\s*[-–]\s*", "", tekst)
        tekst = tekst.strip()
        if (5 < len(tekst) < 80
                and not any(skip in tekst.lower() for skip in [
                    "bekijk", "contact", "vacature", "over ons", "service",
                    "nieuws", "lease", "verzeker", "financier", "privacy",
                    "cookie", "disclaimer", "werkplaats", "aanbod", "modellen"
                ])):
            gevonden.add(tekst)

    # Methode 2: gerichte patronen
    extra_patronen = [
        r"Apple CarPlay", r"Android Auto", r"Keyless[- ]?(?:entry|go|start)",
        r"Climate [Cc]ontrol", r"Airconditioning", r"Elektroni?sch dashboard",
        r"Navigatiesysteem", r"Warmtewerend glas", r"Achterbank deelbaar",
        r"Lendesteunen?", r"Sportstoel(?:en)?", r"Sportstuur",
        r"Stuurwiel leer", r"Stuurwiel multifunctioneel",
        r"360.?camera", r"Parkeersensoren?", r"Achteruitrijcamera",
        r"Adaptieve cruise", r"Lane assist", r"Dodehoek",
        r"Elektrisch verstelbare? stoelen?", r"Elektrisch verstelbare? zetels?",
        r"Geheugenfunctie", r"Massagefunctie",
        r"Draadloos opladen", r"Draadloos oplaadsysteem",
        r"DAB\+?", r"Burmester", r"Harman Kardon",
        r"Augmented [Rr]eality", r"Head.up display",
        r"Trekhaak met ESP", r"Aanhangwagenstabilisatie",
        r"Winter[- ]?[Pp]ack", r"Premium Plus pakket",
        r"Lichtmetalen velgen", r"AMG velgen",
        r"Regensensor", r"Automatisch dimmende",
        r"Verwarmde? (?:zetels?|stoelen?|voorstoelen?|voorruit|spiegels?|stuurwiel)",
        r"Stoelcomfortpakket", r"Lendensteun",
    ]
    for pat in extra_patronen:
        m = re.search(pat, full_text, re.IGNORECASE)
        if m:
            gevonden.add(m.group(0).strip())

    # Filter bekende opties eruit
    gefilterd = set()
    for opt in gevonden:
        opt_lower = opt.lower()
        if not any(bk in opt_lower for bk in BEKENDE_OPTIES):
            gefilterd.add(opt)

    return gefilterd  # geeft SET terug


# ─────────────────────────────────────────────
# PRIJSEXTRACTIE
# ─────────────────────────────────────────────
def extract_prices(full_text, domain, soup=None):
    vraagprijs = "?"
    actieprijs = "-"

    if "autotrack" in domain:
        m = re.search(r"Prijs\s+(?:incl\.?\s*btw\s+)?€\s?([\d.,]+)", full_text, re.IGNORECASE)
        if m:
            vraagprijs = "€ " + m.group(1)
        a = re.search(r"(?:actieprijs|van)\s+€\s?([\d.,]+)", full_text, re.IGNORECASE)
        if a:
            actieprijs = "€ " + a.group(1)
        return vraagprijs, actieprijs

    if "autoscout24" in domain:
        m = re.search(r"€\s?([\d.]+)", full_text)
        if m:
            vraagprijs = "€ " + m.group(1)
        return vraagprijs, actieprijs

    return _generic_prices(full_text)


def _generic_prices(full_text):
    vraagprijs = "?"
    actieprijs = "-"
    raw = re.findall(r"€\s?([\d.,]+)", full_text)
    parsed = []
    for p in raw:
        try:
            val = float(p.replace(".", "").replace(",", "."))
            if val >= 5000:
                parsed.append((val, "€ " + p))
        except ValueError:
            pass
    seen_vals = set()
    unique = []
    for val, label in parsed:
        if val not in seen_vals:
            seen_vals.add(val)
            unique.append((val, label))
    unique.sort(key=lambda x: x[0], reverse=True)
    if len(unique) >= 2:
        vraagprijs = unique[0][1]
        actieprijs = unique[1][1]
    elif len(unique) == 1:
        vraagprijs = unique[0][1]
    return vraagprijs, actieprijs


# ─────────────────────────────────────────────
# AUTOTRACK SPECS
# ─────────────────────────────────────────────
def scrape_autotrack(full_text):
    result = {}
    result["Bouwjaar"] = re_val(r"Bouwjaar\s+(\d{4})", full_text)
    result["Kilometerstand"] = re_val(r"Kilometerstand\s+([\d.,]+\s?km)", full_text)
    result["Brandstof"] = re_val(r"Brandstof\s+([A-Za-z /]+?)(?:\s+Transmissie|\s+Verbruik|\|)", full_text)

    vsb_raw = re_val(r"Transmissietype\s+([A-Za-z]+)", full_text)
    if vsb_raw == "?":
        vsb_raw = re_val(r"Versnellingsbak\s+([A-Za-z]+)", full_text)
    if re.search(r"automaat|automatic|dsg|dct", vsb_raw, re.IGNORECASE):
        result["Versnellingsbak"] = "Automaat"
    elif re.search(r"hand|manueel|manual", vsb_raw, re.IGNORECASE):
        result["Versnellingsbak"] = "Handgeschakeld"
    else:
        result["Versnellingsbak"] = vsb_raw

    verm = re_val(r"Vermogen\s+([\d]+\s?pk\s*\([\d]+\s?kW\))", full_text)
    if verm == "?":
        verm = re_val(r"Vermogen\s+([\d]+\s?(?:pk|kW))", full_text)
    result["Vermogen"] = verm

    result["Carrosserie"] = re_val(r"Carrosserie(?:type)?\s+([A-Za-z /]+?)(?:\s+\||\s{2,}|Download|$)", full_text)

    if re.search(r"Prijs\s+incl\.?\s*btw", full_text, re.IGNORECASE):
        result["BTW/Marge"] = "BTW"
    elif re.search(r"marge", full_text, re.IGNORECASE):
        result["BTW/Marge"] = "Marge"
    else:
        result["BTW/Marge"] = "?"

    result["APK"] = re_val(r"APK\s+geldig\s+tot\s*[-–]?\s*([A-Za-z0-9 ]+?)(?:\s*[-–]|\s*Kenteken|\|)", full_text)

    kleur = re_val(r"Kleur\s+([A-Za-z]+)(?:\s|\|)", full_text)
    result["Kleur exterieur"] = kleur.capitalize() if kleur != "?" else find_color(full_text)
    result["Laksoort"] = re_val(r"(?:Laksoort|Soort lak)\s+([A-Za-z]+)", full_text)
    result["Kleur interieur"] = re_val(r"(?:Kleur interieur|Interieurkleur)\s+([A-Za-z]+)", full_text)

    bekleding_map = [
        ("half leder", "Half leder"), ("alcantara", "Alcantara"),
        ("artico", "Artico (kunstleder)"), ("microvezel", "Microvezel"),
        ("leder", "Leder"), ("leather", "Leder"), ("stof", "Stof"),
        ("skai", "Skai (kunstleder)"),
    ]
    result["Bekleding"] = next((lbl for kw, lbl in bekleding_map if kw in full_text.lower()), "?")
    result["Garantie"] = re_val(r"Garantie\s+([^\|]+?)(?:\s*\||\s{2,}|$)", full_text)
    return result


# ─────────────────────────────────────────────
# HOOFD SCRAPER
# ─────────────────────────────────────────────
def scrape_page(url):
    E = "?"
    result = {"URL": url}
    domain = urlparse(url).netloc

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        result["Titel"] = f"Fout: {e}"
        return result

    soup = BeautifulSoup(resp.text, "html.parser")
    full_text = soup.get_text(separator=" ", strip=True)
    result["_raw_text"] = full_text

    is_autotrack = "autotrack" in domain

    h1 = soup.find("h1")
    result["Titel"] = (h1.get_text(" ", strip=True)[:90] if h1
                       else (soup.title.string[:90] if soup.title else E))
    result["Dealer"] = domain.replace("www.", "")
    result["Vraagprijs"], result["Actieprijs"] = extract_prices(full_text, domain, soup)

    if is_autotrack:
        result.update(scrape_autotrack(full_text))
    else:
        ym = re.search(r"(?:bouwjaar|jaar van|eerste toelating)[^\d]*\b(19[5-9]\d|20[0-2]\d)\b", full_text, re.IGNORECASE)
        if not ym:
            ym = re.search(r"\b(20[0-2]\d|19[5-9]\d)\b", full_text)
        result["Bouwjaar"] = ym.group(1) if ym else E

        km = re.search(r"\b(\d{1,3}(?:[.,]\d{3})+|\d{5,})\s?km\b", full_text, re.IGNORECASE)
        result["Kilometerstand"] = km.group(0).strip() if km else E

        fuel_map = [
            ("hybride benzine", "Hybride benzine"), ("elektro/benzine", "Hybride (Elektro/Benzine)"),
            ("plug-in", "Plug-in hybride"), ("elektrisch", "Elektrisch"),
            ("diesel", "Diesel"), ("benzine", "Benzine"), ("lpg", "LPG"),
        ]
        result["Brandstof"] = next((lbl for kw, lbl in fuel_map if kw in full_text.lower()), E)

        pwr = re.search(r"(\d{2,4})\s?kW\s*[/(]\s*(\d{2,4})\s*[Pp][Kk]", full_text)
        result["Vermogen"] = f"{pwr.group(1)} kW / {pwr.group(2)} pk" if pwr else re_val(r"(\d{2,4})\s?(pk|kW|hp)", full_text, default=E)

        if re.search(r"\bautomaat\b|\bautomatic\b|\bdsg\b|\bdct\b", full_text, re.IGNORECASE):
            result["Versnellingsbak"] = "Automaat"
        elif re.search(r"\bhandgeschakeld\b|\bhandmatig\b|\bmanual\b", full_text, re.IGNORECASE):
            result["Versnellingsbak"] = "Handgeschakeld"
        else:
            result["Versnellingsbak"] = E

        body_map = [
            (r"suv|off.road", "SUV"), (r"\bsedan\b", "Sedan"), (r"\bhatchback\b", "Hatchback"),
            (r"stationwagon|station wagon", "Stationwagon"), (r"coupé|coupe", "Coupé"),
            (r"cabriolet|cabrio", "Cabriolet"), (r"\bmpv\b|\bvan\b", "MPV/Van"),
        ]
        result["Carrosserie"] = next((lbl for pat, lbl in body_map if re.search(pat, full_text, re.IGNORECASE)), E)
        result["BTW/Marge"] = "BTW" if re.search(r"\bbtw\b", full_text, re.IGNORECASE) else ("Marge" if re.search(r"\bmarge\b", full_text, re.IGNORECASE) else E)

        apk = re.search(r"APK[\s:]+([\d]{2}[/-][\d]{4}|[\d]{4})", full_text, re.IGNORECASE)
        result["APK"] = apk.group(1) if apk else E
        gar = re.search(r"garantie[\s:]+(\d+\s?\w+)", full_text, re.IGNORECASE)
        result["Garantie"] = gar.group(1).strip() if gar else E

        ext_color = E
        m = re.search(r"(?:kleur|fabriekskleur)[^\n:]*?:\s*([A-Za-z][A-Za-z\s]{1,25})(?:\s{2,}|\n|,|\|)", full_text, re.IGNORECASE)
        if m:
            c = m.group(1).strip()
            if not any(x in c.lower() for x in ["interieur", "bekleding", "lak", "soort"]):
                ext_color = c.capitalize()
        result["Kleur exterieur"] = ext_color if ext_color != E else find_color(full_text)

        lak = re.search(r"(?:soort lak|laksoort)[\s:]+([A-Za-z]+)", full_text, re.IGNORECASE)
        result["Laksoort"] = lak.group(1).capitalize() if lak else E

        int_color = E
        for pat in [r"kleur interieur[\s:]+([A-Za-z][A-Za-z\s]{1,20})(?:\s{2,}|\n|,|\|)", r"interieurkleur[\s:]+([A-Za-z][A-Za-z\s]{1,20})(?:\s{2,}|\n|,|\|)"]:
            m = re.search(pat, full_text, re.IGNORECASE)
            if m:
                int_color = m.group(1).strip().capitalize()
                break
        result["Kleur interieur"] = int_color

        bekleding_map = [
            ("half leder", "Half leder"), ("alcantara", "Alcantara"), ("artico", "Artico (kunstleder)"),
            ("microvezel", "Microvezel"), ("leder", "Leder"), ("leather", "Leder"),
            ("stof", "Stof"), ("skai", "Skai (kunstleder)"),
        ]
        result["Bekleding"] = next((lbl for kw, lbl in bekleding_map if kw in full_text.lower()), E)

    # Vaste opties
    result["Trekhaak"]              = heeft_optie(full_text, r"\btrekhaak\b")
    result["Panoramadak"]           = heeft_optie(full_text, r"\bpanorama\w*\b", r"\bschuifdak\b")
    result["AMG-styling"]           = heeft_optie(full_text, r"\bamg.styling\b", r"\bamg.bodykit\b", r"\bamg.line\b")
    result["Dakrailing"]            = heeft_optie(full_text, r"\bdakrail\w*\b", r"\bdakreling\b")
    result["LED koplampen"]         = heeft_optie(full_text, r"\bmultibeam\b", r"\bmatrix\s+led\b", r"\bled\s+koplamp\w*\b")
    result["Stoelverwarming"]       = heeft_optie(full_text, r"\bstoelverwarming\b", r"\bverwarmde?\s+(stoelen?|zetels?|voorstoelen?)\b", r"\bzetels?\s+verwarmd\b")
    result["Elektrische stoelen"]   = heeft_optie(full_text, r"\belektrisch\s+verstelbare?\s+(stoelen?|zetels?)\b", r"\bstoel\w*\s+elektrisch\s+verstelbaar\b")
    result["Sfeerverlichting"]      = heeft_optie(full_text, r"\bsfeerverlichting\b")
    result["Navigatie"]             = heeft_optie(full_text, r"\bnavigati\w+\b", r"\bmbux\b")
    result["Head-up display"]       = heeft_optie(full_text, r"\bhead.up\b")
    result["CarPlay / Android Auto"]= heeft_optie(full_text, r"\bcarplay\b", r"\bandroid auto\b", r"\bapple carplay\b", r"\bsmartphone integratie\b")
    result["Cruise control"]        = heeft_optie(full_text, r"\bcruise\s*control\b", r"\btempomat\b", r"\bsnelheidsregelaar\b", r"\badaptieve cruise\b")
    result["Keyless"]               = heeft_optie(full_text, r"\bkeyless\b")
    result["Climate control"]       = heeft_optie(full_text, r"\bclimate\s*control\b", r"\bthermotronic\b", r"\bautomatische klimaat\b")
    result["360° camera"]           = heeft_optie(full_text, r"\b360.?camera\b", r"\bromcamera\b", r"\bparkeerpakket\b")
    result["Trekgewicht"]           = re_val(r"Trekgewicht\s+(?:max\.?\s*)?([\d.,]+\s?kg)", full_text, default="-")

    # Extra opties als SET opslaan
    result["_extra_opties_set"] = extract_extra_opties(soup, full_text)

    return result


# ─────────────────────────────────────────────
# UI
# ─────────────────────────────────────────────
st.subheader("🔗 Voer advertentie-links in")
cols_input = st.columns(3)
urls = []
for i, col in enumerate(cols_input):
    with col:
        u = st.text_input(f"Auto {i+1}", placeholder="https://...", key=f"url_{i}")
        urls.append(u.strip())

debug_mode = st.checkbox("🛠️ Debug-modus (toon ruwe paginatekst per auto)")

if st.button("🔍 Vergelijk auto's", type="primary"):
    active_urls = [u for u in urls if u]
    if len(active_urls) < 2:
        st.warning("Voer minimaal 2 links in.")
    else:
        with st.spinner("Gegevens ophalen..."):
            cars = [scrape_page(u) for u in active_urls]

        labels = [f"Auto {i+1}" for i in range(len(cars))]

        def tabel(titel, velden):
            st.markdown(f"### {titel}")
            rows = {"Kenmerk": velden}
            for i, car in enumerate(cars):
                rows[labels[i]] = [car.get(v, "?") for v in velden]
            df = pd.DataFrame(rows).set_index("Kenmerk")
            st.dataframe(df, use_container_width=True)

        tabel("📋 Algemene gegevens", [
            "Titel", "Dealer", "Vraagprijs", "Actieprijs",
            "Bouwjaar", "Kilometerstand", "Brandstof",
            "Vermogen", "Versnellingsbak", "Carrosserie",
            "BTW/Marge", "APK", "Garantie",
        ])

        tabel("🚘 Exterieur", [
            "Kleur exterieur", "Laksoort",
            "Trekhaak", "Trekgewicht", "Panoramadak",
            "AMG-styling", "Dakrailing", "LED koplampen",
        ])

        tabel("🪑 Interieur & comfort", [
            "Kleur interieur", "Bekleding",
            "Stoelverwarming", "Elektrische stoelen",
            "Sfeerverlichting", "Climate control",
            "Navigatie", "Head-up display",
            "CarPlay / Android Auto", "Cruise control",
            "Keyless", "360° camera",
        ])

        # ── Extra opties vergelijkingstabel ──
        st.markdown("### 🔧 Extra opties vergelijking")

        # Alle unieke opties samenvoegen over alle auto's
        alle_opties = set()
        for car in cars:
            alle_opties.update(car.get("_extra_opties_set", set()))

        if alle_opties:
            rows_extra = {"Optie": sorted(alle_opties)}
            for i, car in enumerate(cars):
                car_opties = car.get("_extra_opties_set", set())
                # Case-insensitive match
                car_opties_lower = {o.lower() for o in car_opties}
                rows_extra[labels[i]] = [
                    "✅" if opt.lower() in car_opties_lower else "❌"
                    for opt in sorted(alle_opties)
                ]
            df_extra = pd.DataFrame(rows_extra).set_index("Optie")
            st.dataframe(df_extra, use_container_width=True)
        else:
            st.info("Geen extra opties gevonden voor deze auto's.")

        st.markdown("### 🔗 Bronlinks")
        for i, car in enumerate(cars):
            st.markdown(f"**Auto {i+1}:** [{car.get('Titel', '-')}]({car['URL']})")

        if debug_mode:
            st.markdown("---")
            st.subheader("🛠️ Debug: ruwe paginatekst")
            for i, car in enumerate(cars):
                with st.expander(f"Auto {i+1} — {car.get('Titel', car['URL'])}"):
                    raw = car.get("_raw_text", "Geen tekst beschikbaar.")
                    st.text_area("Ruwe tekst (eerste 3000 tekens)", raw[:3000], height=300)
                    st.caption(f"Totale tekstlengte: {len(raw)} tekens")
