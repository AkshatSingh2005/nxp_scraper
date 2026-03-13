import csv
import time
import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


BASE = "https://www.nxp.com"
PRODUCTS_ROOT = "https://www.nxp.com/products"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; NXP-Full-Scraper/1.0)"
}


# -------------------------------------------------
# HTTP FETCH
# -------------------------------------------------

def fetch(url):

    print("GET:", url)

    resp = requests.get(url, headers=HEADERS, timeout=30)

    resp.raise_for_status()

    return resp.text


# -------------------------------------------------
# ROHS GRADE CONVERSION
# -------------------------------------------------

def nxp_env_to_rohs_grade(pb_free, eu_rohs, halogen_free):

    pb = (pb_free or "").lower().strip()
    rohs = (eu_rohs or "").lower().strip()
    hal = (halogen_free or "").lower().strip()

    if rohs == "yes" and pb == "yes" and hal == "yes":
        return "Ecopack1"

    elif rohs == "yes" and pb == "yes":
        return "Ecopack2"

    elif rohs == "yes":
        return "Ecopack3"

    return ""


# -------------------------------------------------
# DISCOVER SERIES PAGES
# -------------------------------------------------

def discover_series_pages():

    html = fetch(PRODUCTS_ROOT)

    soup = BeautifulSoup(html, "html.parser")

    series_urls = set()

    for a in soup.select("a[href^='/products/']"):

        href = a.get("href")

        if href and ":" in href:

            series_urls.add(urljoin(BASE, href))

    print("\nSERIES DISCOVERED:", len(series_urls))

    for s in list(series_urls)[:10]:

        print("Series example:", s)

    return list(series_urls)


# -------------------------------------------------
# PARSE SERIES TABLE
# -------------------------------------------------

def parse_series_table(html):

    soup = BeautifulSoup(html, "html.parser")

    table = soup.select_one("table.comparisonTable")

    if not table:
        return []

    products = []

    current_group = ""

    for row in table.select("tbody tr"):

        cells = row.select("td")

        if not cells:
            continue

        if cells[0].get("rowspan"):

            current_group = cells[0].get_text(" ", strip=True)

            offset = 1

        else:

            offset = 0

        if len(cells) < offset + 2:
            continue

        link = cells[offset].select_one("a[href^='/products/']")

        if not link:
            continue

        product_url = urljoin(BASE, link["href"])

        product_label = link.get_text(strip=True)

        products.append({

            "series_group": current_group,
            "product_label": product_label,
            "product_url": product_url
        })

    print("Products discovered in series:", len(products))

    return products


# -------------------------------------------------
# PARSE PRODUCT PAGE
# -------------------------------------------------

def parse_product_page(html):

    soup = BeautifulSoup(html, "html.parser")

    result = {
        "product_name": "",
        "product_status": "",
        "short_description": "",
        "key_features": "",
        "datasheet_url": "",
        "package_quality_url": "",
        "buy_parametrics_url": ""
    }

    h1 = soup.find("h1")

    if h1:

        result["product_name"] = h1.get_text(strip=True)

    for tag in soup.find_all(["span","div"]):

        t = tag.get_text(strip=True).upper()

        if t in ["ACTIVE","END OF LIFE","DISCONTINUED"]:

            result["product_status"] = t

            break

    if h1:

        p = h1.find_next("p")

        if p:

            result["short_description"] = p.get_text(" ",strip=True)

    feats = []

    for h in soup.find_all(["h2","h3"]):

        if "key features" in h.get_text().lower():

            ul = h.find_next("ul")

            if ul:

                for li in ul.find_all("li"):

                    feats.append(li.get_text(strip=True))

            break

    result["key_features"] = "; ".join(feats)

    for a in soup.select("a[href$='.pdf']"):

        if "data" in a.get_text().lower():

            result["datasheet_url"] = urljoin(BASE,a["href"])

            break

    for a in soup.select("a"):

        txt = a.get_text(" ",strip=True).upper()

        if "PACKAGE/QUALITY" in txt:

            result["package_quality_url"] = urljoin(BASE,a["href"])

        if "BUY/PARAMETRICS" in txt:

            result["buy_parametrics_url"] = urljoin(BASE,a["href"])

    return result


# -------------------------------------------------
# PARSE ENVIRONMENT TABLE
# -------------------------------------------------

def parse_env_table(html):

    soup = BeautifulSoup(html, "html.parser")

    table = soup.select_one("article#Environmental_Information table")

    if not table:
        return []

    rows = []

    for tr in table.select("tbody tr"):

        tds = tr.select("td")

        if len(tds) < 8:
            continue

        rows.append({

            "PRODUCT_PART_NUMBER": tds[0].get_text(strip=True),

            "PACKAGING_DESCR": tds[1].get_text(strip=True),

            "MARKETING_STATUS": tds[2].get_text(strip=True),

            "PB_FREE": tds[3].get_text(strip=True),

            "EU_ROHS": tds[4].get_text(strip=True),

            "HALOGEN_FREE": tds[5].get_text(strip=True),

            "RHF_INDICATOR": tds[6].get_text(strip=True),

            "REACH_SVHC": tds[7].get_text(strip=True)

        })

    return rows


# -------------------------------------------------
# MAIN SCRAPER
# -------------------------------------------------

def build_rows():

    rows = []

    series_pages = discover_series_pages()

    for series in series_pages:

        print("\nSCRAPING SERIES:", series)

        try:

            html_series = fetch(series)

            product_groups = parse_series_table(html_series)

        except:

            continue

        for group in product_groups:

            product_url = group["product_url"]

            time.sleep(1)

            try:

                html_prod = fetch(product_url)

                prod = parse_product_page(html_prod)

            except:

                continue

            pq_url = prod["package_quality_url"]

            if not pq_url:

                pq_url = product_url + "?tab=Package_Quality_Tab"

            try:

                pq_html = fetch(pq_url)

                env_rows = parse_env_table(pq_html)

            except:

                continue

            for env in env_rows:

                rohs = nxp_env_to_rohs_grade(

                    env["PB_FREE"],
                    env["EU_ROHS"],
                    env["HALOGEN_FREE"]
                )

                row = {

                    "SUPPLIER":"NXP",

                    "PRODUCT_PART_NUMBER":env["PRODUCT_PART_NUMBER"],

                    "PACKAGING_DESCR":env["PACKAGING_DESCR"],

                    "MARKETING_STATUS":env["MARKETING_STATUS"],

                    "ROHS_COMPLIANCE_GRADE":rohs,

                    "PRODUCT_URL":product_url,

                    "PARAMETRICS_URL":prod["buy_parametrics_url"],

                    "DATASHEET_URL":prod["datasheet_url"],

                    "KEY_FEATURES":prod["key_features"],

                    "SHORT_DESCRIPTION":prod["short_description"],

                    "PB_FREE":env["PB_FREE"],

                    "EU_ROHS":env["EU_ROHS"],

                    "HALOGEN_FREE":env["HALOGEN_FREE"],

                    "RHF_INDICATOR":env["RHF_INDICATOR"],

                    "REACH_SVHC":env["REACH_SVHC"]
                }

                rows.append(row)

    return rows


# -------------------------------------------------
# SAVE CSV
# -------------------------------------------------

def save_csv(rows):

    if not rows:

        print("No rows collected.")

        return

    fields = list(rows[0].keys())

    with open("nxp_full_catalog.csv","w",newline="",encoding="utf-8") as f:

        writer = csv.DictWriter(f,fields)

        writer.writeheader()

        writer.writerows(rows)

    print("\nSaved",len(rows),"rows")


# -------------------------------------------------
# RUN
# -------------------------------------------------

if __name__ == "__main__":

    rows = build_rows()

    save_csv(rows)