
import csv
import time
import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE = "https://www.nxp.com"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ST-Internal-Scraper/1.0)",
}


# -------------------------
# Utility helpers
# -------------------------

def fetch(url: str) -> str:
    print(f"GET {url}")
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.text


def nxp_env_to_rohs_grade(pb_free: str, eu_rohs: str, halogen_free: str) -> str:
    pb = (pb_free or "").strip().lower()
    rohs = (eu_rohs or "").strip().lower()
    hal = (halogen_free or "").strip().lower()

    if rohs == "yes" and pb == "yes" and hal == "yes":
        return "Ecopack1"
    elif rohs == "yes" and pb == "yes":
        return "Ecopack2"
    elif rohs == "yes":
        return "Ecopack3"  # optional
    else:
        return ""


# -------------------------
# 1. Parse MCX A Series table (series-level product groups)
# -------------------------

MCX_A_SERIES_URL = (
    "https://www.nxp.com/products/processors-and-microcontrollers/"
    "arm-microcontrollers/general-purpose-mcus/mcx-arm-cortex-m/"
    "mcx-a-series-microcontrollers:MCX-A-SERIES"
)


def parse_mcx_a_series_table(html: str):
    """
    Returns a list of product-group entries like:
    {
      "series_group": "MCX A1 Essential",
      "product_label": "MCX A13",
      "product_url": "https://www.nxp.com/products/MCX-A13X-A14X-A15X",
      "packages_overview": "H-PQFN32, HVQFN48, LQFP48",
      "main_clock": "96MHz",
      "flash_summary": "64 kB to 128 kB",
      "features_summary": "ADC, I3C",
    }
    """
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("div#Products table.comparisonTable")
    if not table:
        print("MCX A Series products table not found.")
        return []

    products = []
    current_series_group = ""

    for row in table.select("tbody tr"):
        cells = row.select("td")
        if not cells:
            continue

        # First column may have series group with rowspan
        if cells[0].get("rowspan"):
            series_text = cells[0].get_text(" ", strip=True)
            # e.g. "MCX A1 Essential" (with line break)
            current_series_group = re.sub(r"\s+", " ", series_text)

            # Remaining columns are product info
            offset = 1
        else:
            offset = 0  # series group from previous row

        if len(cells) < offset + 5:
            continue

        prod_td = cells[offset]
        link = prod_td.select_one("a[href^='/products/']")
        if not link:
            continue

        product_label = link.get_text(strip=True)
        product_url = urljoin(BASE, link["href"])

        main_clock = cells[offset + 1].get_text(strip=True)
        flash_summary = cells[offset + 2].get_text(strip=True)
        features_summary = cells[offset + 3].get_text(strip=True)
        packages_overview = cells[offset + 4].get_text(strip=True)

        products.append({
            "series_group": current_series_group,
            "product_label": product_label,
            "product_url": product_url,
            "main_clock": main_clock,
            "flash_summary": flash_summary,
            "features_summary": features_summary,
            "packages_overview": packages_overview,
        })

    return products


# -------------------------
# 2. Parse product page: title, status, short description, key features, datasheet URL
# -------------------------

def parse_product_page(html: str, product_url: str):
    soup = BeautifulSoup(html, "html.parser")
    result = {
        "product_name": "",
        "product_status": "",
        "short_description": "",
        "key_features": "",
        "buy_parametrics_url": "",
        "package_quality_url": "",
        "datasheet_url": "",
    }

    # Title (H1) – often in .page-title or similar
    # For robustness search first h1
    h1 = soup.find("h1")
    if h1:
        result["product_name"] = h1.get_text(" ", strip=True)

    # Status (ACTIVE, etc.) – often near title; look for element with text "ACTIVE"
    status_el = soup.find(lambda tag: tag.name in ["span", "div"] and
                          tag.get_text(strip=True).upper() in ("ACTIVE", "NOT RECOMMENDED FOR NEW DESIGNS",
                                                                "END OF LIFE", "DISCONTINUED"))
    if status_el:
        result["product_status"] = status_el.get_text(strip=True)

    # Short description – usually the first <p> under the title
    # Heuristic: find first <p> after H1
    short_desc = ""
    if h1:
        for sib in h1.find_all_next():
            if sib.name == "p":
                short_desc = sib.get_text(" ", strip=True)
                break
    result["short_description"] = short_desc

    # Key Features – heading "Key Features" then <ul><li>
    key_feats = []
    for heading in soup.find_all(["h2", "h3", "h4"]):
        if "key features" in heading.get_text(strip=True).lower():
            # collect li under next siblings until next heading
            for sib in heading.find_next_siblings():
                if sib.name in ["h2", "h3", "h4"]:
                    break
                for li in sib.find_all("li"):
                    txt = li.get_text(" ", strip=True)
                    if txt:
                        key_feats.append(txt)
            break
    result["key_features"] = "; ".join(key_feats)

    # Buttons BUY/PARAMETRICS and PACKAGE/QUALITY
    for a in soup.select("a"):
        txt = a.get_text(" ", strip=True).upper()
        if "BUY/PARAMETRICS" in txt and a.has_attr("href"):
            result["buy_parametrics_url"] = urljoin(BASE, a["href"])
        elif "PACKAGE/QUALITY" in txt and a.has_attr("href"):
            result["package_quality_url"] = urljoin(BASE, a["href"])

    # Datasheet URL – from Documentation tab
    # We try to find any link with "Data Sheet" or "Datasheet" near.
    doc_link = None
    for a in soup.select("a[href$='.pdf']"):
        t = a.get_text(" ", strip=True).lower()
        if "data sheet" in t or "datasheet" in t:
            doc_link = a["href"]
            break
    if doc_link:
        result["datasheet_url"] = urljoin(BASE, doc_link)

    return result


# -------------------------
# 3. Parse Package/Quality -> Environmental Information table
# -------------------------

def parse_env_table(html: str):
    soup = BeautifulSoup(html, "html.parser")
    result = []

    table = soup.select_one("article#Environmental_Information table")
    if not table:
        print("Environmental Information table not found.")
        return result

    for row in table.select("tbody tr"):
        cells = row.select("td")
        if len(cells) < 8:
            continue

        # Part / Package cell
        part_pkg_td = cells[0]

        pn_a = part_pkg_td.find("a", href=re.compile(r"/part/"))
        if not pn_a:
            pn_a = part_pkg_td.find("a")
        part_number = pn_a.get_text(strip=True) if pn_a else ""

        pkg_a = part_pkg_td.find("a", href=re.compile(r"/packages/"))
        package_descr = pkg_a.get_text(strip=True) if pkg_a else ""

        status = cells[2].get_text(strip=True)
        pb_free = cells[3].get_text(strip=True)

        eu_rohs_cell = cells[4]
        eu_rohs_text = eu_rohs_cell.get_text(" ", strip=True)
        eu_rohs = "Yes" if "yes" in eu_rohs_text.lower() else "No"

        halogen_free = cells[5].get_text(strip=True)
        rhf_indicator = cells[6].get_text(strip=True)
        reach_text = cells[7].get_text(" ", strip=True)

        result.append({
            "PRODUCT_PART_NUMBER": part_number,
            "PACKAGING_DESCR": package_descr,
            "MARKETING_STATUS": status,
            "PB_FREE": pb_free,
            "EU_ROHS": eu_rohs,
            "HALOGEN_FREE": halogen_free,
            "RHF_INDICATOR": rhf_indicator,
            "REACH_SVHC": reach_text,
        })

    return result


# -------------------------
# 4. Main: build final rows (partial sample: only first ~6 parts)
# -------------------------

def build_rows(limit_parts: int = 6):
    rows = []

    # Fixed hierarchy path for this branch
    H0 = "Processors and Microcontrollers"
    H1 = "Arm Microcontrollers"
    H2 = "General Purpose MCUs"
    H3 = "MCX Arm Cortex-M"
    H4 = "MCX A Series Microcontrollers"

    # Load MCX A Series page and parse the products table
    html_series = fetch(MCX_A_SERIES_URL)
    product_groups = parse_mcx_a_series_table(html_series)

    for group in product_groups:
        product_url = group["product_url"]
        time.sleep(1.0)
        html_prod = fetch(product_url)
        prod_info = parse_product_page(html_prod, product_url)

        # If PACKAGE/QUALITY URL not found from product page,
        # construct a common pattern: append "?tab=Package_Quality" if needed.
        pkgq_url = prod_info["package_quality_url"]
        if not pkgq_url:
            # Fallback guess – may need adjustment
            pkgq_url = product_url + "?tab=Package_Quality"

        time.sleep(1.0)
        try:
            html_pq = fetch(pkgq_url)
        except Exception as e:
            print(f"Failed to fetch Package/Quality for {product_url}: {e}")
            continue

        env_rows = parse_env_table(html_pq)
        if not env_rows:
            continue

        for env in env_rows:
            rohs_grade = nxp_env_to_rohs_grade(
                env["PB_FREE"], env["EU_ROHS"], env["HALOGEN_FREE"]
            )

            # Decide grade (Automotive vs Industrial) – for MCX A assume "Industrial"
            grade = "Industrial"

            rec = {
                # ST-like core fields
                "PROD_CLASS_ID": "",  # you can fill later
                "PROD_CLASS_NAME": H1,  # e.g. we use "Arm Microcontrollers"
                "SUB_CLASS_ID": "",
                "SUB_CLASS_NAME": H2,   # "General Purpose MCUs"
                "PRODUCT_CODE": "",
                "PRODUCT_PART_NUMBER": env["PRODUCT_PART_NUMBER"],
                "PACKAGING_CODE": "",
                "PACKAGING_DESCR": env["PACKAGING_DESCR"],
                "ECCN_US": "",
                "ECCN_EU": "",
                "SUPPLIER": "NXP",
                "FREE_SAMPLES": "",  # could be filled from store later
                "COUNTRY_OF_ORIGIN": "",
                "ROHS_COMPLIANCE_GRADE": rohs_grade,
                "GRADE": grade,
                "MARKETING_STATUS": env["MARKETING_STATUS"],

                # Full hierarchy
                "HIERARCHY_L0_CATEGORY": H0,
                "HIERARCHY_L1_SUBCATEGORY": H1,
                "HIERARCHY_L2_GROUP": H2,
                "HIERARCHY_L3_FAMILY": H3,
                "HIERARCHY_L4_SERIES": H4,
                "HIERARCHY_L5_PRODUCT_GROUP": prod_info["product_name"],

                # URLs
                "PRODUCT_URL": product_url,
                "PARAMETRICS_URL": prod_info["buy_parametrics_url"],
                "DATASHEET_URL": prod_info["datasheet_url"],

                # Product description & features
                "KEY_FEATURES": prod_info["key_features"],
                "SHORT_DESCRIPTION": prod_info["short_description"],

                # Environmental raw flags
                "PB_FREE": env["PB_FREE"],
                "EU_ROHS": env["EU_ROHS"],
                "HALOGEN_FREE": env["HALOGEN_FREE"],
                "RHF_INDICATOR": env["RHF_INDICATOR"],
                "REACH_SVHC": env["REACH_SVHC"],

                # Store/commercial (not filled yet)
                "PRICE_STORE": "",
                "STOCK_STORE": "",
                "HAS_DISTRIBUTOR_LINK": "",
            }

            rows.append(rec)
            if len(rows) >= limit_parts:
                return rows

    return rows


def save_csv(rows, filename="nxp_mcx_sample.csv"):
    if not rows:
        print("No rows to save.")
        return
    fieldnames = list(rows[0].keys())
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Saved {len(rows)} rows to {filename}")


if __name__ == "__main__":
    sample_rows = build_rows(limit_parts=6)
    for r in sample_rows:
        print(r)
        print("-" * 80)
    save_csv(sample_rows)

