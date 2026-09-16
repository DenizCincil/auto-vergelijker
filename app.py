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

def extract_prices(full_text, domain):
    vraagprijs = "?"
    actieprijs = "-"

    if "autoscout24" in domain:
        m = re.search(r"€\s?([\d.]+)", full_text)
        if m:
            vraagprijs = "€ " + m.group(1)
        return vraagprijs, actieprijs

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

    h1 = soup.find("h1")
    result["Titel"] = (h1.get_text(" ", strip=True)[:90] if h1
                       else (soup.title.string[:90] if soup.title else E))
    result["Dealer"] = domain.replace("www.", "")
    result["Vraagprijs"], result["Actieprijs"] = extract_prices(full_text, domain)

    ym = re.search(r"\b(19[5-9]\d|20[0-2]\d)\b", full_text)
    result["Bouwjaar"] = ym.group(0) if ym else E

    km = re.search(r"(\d[\d.]*)\s?km\b", full_text, re.IGNORECASE)
    result["Kilometerstand"] = km.group(0).strip() if km else E

    fuel_map = [
        ("hybride benzine", "Hybride benzine"),
        ("elektro/benzine", "Hybride (Elektro/Benzine)"),
        ("elektrisch", "Elektrisch"),
        ("diesel", "Diesel"),
        ("benzine", "Benzine"),
        ("lpg", "LPG"),
    ]
    result["Brandstof"] = next((lbl for kw, lbl in fuel_map if kw in full_text.lower()), E)

    pwr = re.search(r"(\d{2,4})\s?kW\s*[/(]\s*(\d{2,4})\s*[Pp][Kk]", full_text)
    if pwr:
        result["Vermogen"] = f"{pwr.group(1)} kW / {pwr.group(2)} pk"
    else:
        pwr2 = re.search(r"(\d{2,4})\s?(pk|kW|hp)", full_text, re.IGNORECASE)
        result["Vermogen"] = pwr2.group(0).strip() if pwr2 else E

    if re.search(r"\bautomaat\b|\bautomatic\b|\bautomatisch\b|\bdsg\b|\bdct\b", full_text, re.IGNORECASE):
        result["Versnellingsbak"] = "Automaat"
    elif re.search(r"\bhandgeschakeld\b|\bhandmatig\b|\bmanual\b", full_text, re.IGNORECASE):
        result["Versnellingsbak"] = "Handgeschakeld"
    else:
        result["Versnellingsbak"] = E

    body_map = [
        (r"suv|off.road", "SUV"), (r"\bsedan\b", "Sedan"),
        (r"\bhatchback\b", "Hatchback"), (r"stationwagon", "Stationwagon"),
        (r"coupé|coupe", "Coupé"), (r"cabriolet|cabrio", "Cabriolet"),
    ]
    result["Carrosserie"] = next(
        (lbl for pat, lbl in body_map if re.search(pat, full_text, re.IGNORECASE)), E
    )

    result["BTW/Marge"] = "BTW" if re.search(r"\bbtw\b", full_text, re.IGNORECASE) else (
        "Marge" if re.search(r"\bmarge\b", full_text, re.IGNORECASE) else E)

    apk = re.search(r"APK[\s:]+(\d{2}[/-]\d{4})", full_text, re.IGNORECASE)
    result["APK"] = apk.group(1) if apk else E

    gar = re.search(r"garantie[\s:]+(\d+\s?\w+)", full_text, re.IGNORECASE)
    result["Garantie"] = gar.group(1).strip() if gar else E

    # Exterieur
    ext_color = E
    for pat in [
        r"(?:kleur|fabriekskleur|oorspronkelijke kleur)[\s:]+([A-Za-z][A-Za-z\s]{1,25})(?:\s{2,}|\n|,|\|)",
    ]:
        m = re.search(pat, full_text, re.IGNORECASE)
        if m:
            c = m.group(1).strip()
            if not any(x in c.lower() for x in ["interieur", "bekleding", "lak", "soort"]):
                ext_color = c.capitalize()
                break
    if ext_color == E:
        ext_color = find_color(full_text)
    result["Kleur exterieur"] = ext_color

    lak = re.search(r"(?:soort lak|laksoort)[\s:]+([A-Za-z]+)", full_text, re.IGNORECASE)
    result["Laksoort"] = lak.group(1).capitalize() if lak else E

    result["Trekhaak"] = heeft_optie(full_text, r"\btrekhaak\b")
    result["Panoramadak"] = heeft_optie(full_text, r"\bpanorama\b")
    result["AMG-styling"] = heeft_optie(full_text, r"\bamg.styling\b|\bamg.bodykit\b|\bamg.line\b")
    result["Dakrailing"] = heeft_optie(full_text, r"\bdakrail\w*\b")
    result["LED koplampen"] = heeft_optie(full_text, r"\bled\s+koplamp\w*\b|\bmatrix\s+led\b|\bmultibeam\b")

    # Interieur
    int_color = E
    for pat in [
        r"kleur interieur[\s:]+([A-Za-z][A-Za-z\s]{1,20})(?:\s{2,}|\n|,|\|)",
        r"interieurkleur[\s:]+([A-Za-z][A-Za-z\s]{1,20})(?:\s{2,}|\n|,|\|)",
    ]:
        m = re.search(pat, full_text, re.IGNORECASE)
        if m:
            int_color = m.group(1).strip().capitalize()
            break
    result["Kleur interieur"] = int_color

    bekleding_map = [
        ("half leder", "Half leder"), ("alcantara", "Alcantara"),
        ("artico", "Artico (kunstleder)"), ("microvezel", "Microvezel"),
        ("leder", "Leder"), ("leather", "Leder"), ("stof", "Stof"),
    ]
    result["Bekleding"] = next((lbl for kw, lbl in bekleding_map if kw in full_text.lower()), E)

    result["Stoelverwarming"] = heeft_optie(full_text,
        r"\bstoelverwarming\b", r"\bverwarmde\s+(stoelen|zetels)\b",
        r"\bzetels\s+verwarmd\b", r"\bvoorstoelen\s+verwarmd\b")
    result["Elektrische stoelen"] = heeft_optie(full_text,
        r"\belektrisch\s+verstelbare\s+(stoelen|zetels)\b")
    result["Sfeerverlichting"] = heeft_optie(full_text, r"\bsfeerverlichting\b")
    result["Navigatie"] = heeft_optie(full_text, r"\bnavigati\w+\b", r"\bmbux\b")
    result["Head-up display"] = heeft_optie(full_text, r"\bhead.up\b")
    result["CarPlay / Android Auto"] = heeft_optie(full_text, r"\bcarplay\b", r"\bandroid auto\b")
    result["Cruise control"] = heeft_optie(full_text, r"\bcruise\s*control\b|\btempomat\b")

    return result


# UI
st.subheader("🔗 Voer advertentie-links in")
cols_input = st.columns(3)
urls = []
for i, col in enumerate(cols_input):
    with col:
        u = st.text_input(f"Auto {i+1}", placeholder="https://...", key=f"url_{i}")
        urls.append(u.strip())

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
            "Trekhaak", "Panoramadak", "AMG-styling",
            "Dakrailing", "LED koplampen",
        ])

        tabel("🪑 Interieur & comfort", [
            "Kleur interieur", "Bekleding",
            "Stoelverwarming", "Elektrische stoelen",
            "Sfeerverlichting", "Navigatie", "Head-up display",
            "CarPlay / Android Auto", "Cruise control",
        ])

        st.markdown("### 🔗 Bronlinks")
        for i, car in enumerate(cars):
            st.markdown(f"**Auto {i+1}:** [{car.get('Titel', '-')}]({car['URL']})")