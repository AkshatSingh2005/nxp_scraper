import requests
from bs4 import BeautifulSoup
import csv
import time
from urllib.parse import urljoin

BASE = "https://www.nxp.com"

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


# --------------------------
# HTTP fetch
# --------------------------

def fetch(url):

    print("GET:", url)

    r = requests.get(url, headers=HEADERS, timeout=30)

    r.raise_for_status()

    return r.text


# --------------------------
# Discover category pages
# --------------------------

def discover_categories():

    html = fetch(BASE + "/products")

    soup = BeautifulSoup(html, "html.parser")

    urls = set()

    for a in soup.select("a[href^='/products/']"):

        href = a["href"]

        if ":" in href:
            urls.add(urljoin(BASE, href))

    urls = list(urls)

    print("\nFIRST 10 CATEGORIES FOUND:")

    for u in urls[:10]:
        print(u)

    return urls


# --------------------------
# Discover product pages
# --------------------------

def discover_product_pages(category_urls):

    product_pages = set()

    for url in category_urls:

        print("\nScanning category:", url)

        try:

            html = fetch(url)

            soup = BeautifulSoup(html, "html.parser")

            for a in soup.select("a[href^='/products/']"):

                href = a["href"]

                if "/products/" in href and ":" not in href:

                    product_pages.add(urljoin(BASE, href))

        except Exception as e:

            print("Category scan failed:", url)

            continue

        time.sleep(1)

    product_pages = list(product_pages)

    print("\nFIRST 10 PRODUCT PAGES DISCOVERED:")

    for p in product_pages[:10]:
        print(p)

    return product_pages


# --------------------------
# Parse hierarchy
# --------------------------

def parse_hierarchy(soup):

    levels = ["","","","","",""]

    crumb = soup.select(".breadcrumb a")

    names = [c.get_text(strip=True) for c in crumb]

    for i,n in enumerate(names[:6]):

        levels[i] = n

    return {
        "HIERARCHY_L0_CATEGORY": levels[0],
        "HIERARCHY_L1_SUBCATEGORY": levels[1],
        "HIERARCHY_L2_GROUP": levels[2],
        "HIERARCHY_L3_FAMILY": levels[3],
        "HIERARCHY_L4_SERIES": levels[4],
        "HIERARCHY_L5_PRODUCT_GROUP": levels[5],
    }


# --------------------------
# Parse product page
# --------------------------

def parse_product_page(html):

    soup = BeautifulSoup(html, "html.parser")

    result = {
        "product_name":"",
        "product_status":"",
        "short_description":"",
        "key_features":"",
        "datasheet_url":"",
        "package_quality_url":""
    }

    h1 = soup.find("h1")

    if h1:
        result["product_name"] = h1.get_text(strip=True)

    hierarchy = parse_hierarchy(soup)

    result.update(hierarchy)

    # status

    for s in soup.find_all(["span","div"]):

        txt = s.get_text(strip=True).upper()

        if txt in ["ACTIVE","DISCONTINUED","END OF LIFE"]:

            result["product_status"] = txt

            break

    # description

    if h1:

        p = h1.find_next("p")

        if p:

            result["short_description"] = p.get_text(" ",strip=True)

    # key features

    feats = []

    for h in soup.find_all(["h2","h3"]):

        if "key features" in h.get_text().lower():

            ul = h.find_next("ul")

            if ul:

                for li in ul.find_all("li"):

                    feats.append(li.get_text(strip=True))

            break

    result["key_features"] = "; ".join(feats)

    # datasheet

    for a in soup.select("a[href$='.pdf']"):

        if "data" in a.get_text().lower():

            result["datasheet_url"] = urljoin(BASE,a["href"])

            break

    # package quality

    for a in soup.select("a"):

        if "PACKAGE/QUALITY" in a.get_text().upper():

            result["package_quality_url"] = urljoin(BASE,a["href"])

    return result


# --------------------------
# Parse environmental table
# --------------------------

def parse_env_table(html):

    soup = BeautifulSoup(html,"html.parser")

    rows = []

    table = soup.select_one("article#Environmental_Information table")

    if not table:
        return rows

    for tr in table.select("tbody tr"):

        tds = tr.select("td")

        if len(tds) < 8:
            continue

        env = {

            "PRODUCT_PART_NUMBER": tds[0].get_text(strip=True),

            "PACKAGING_DESCR": tds[1].get_text(strip=True),

            "MARKETING_STATUS": tds[2].get_text(strip=True),

            "PB_FREE": tds[3].get_text(strip=True),

            "EU_ROHS": tds[4].get_text(strip=True),

            "HALOGEN_FREE": tds[5].get_text(strip=True),

            "RHF_INDICATOR": tds[6].get_text(strip=True),

            "REACH_SVHC": tds[7].get_text(strip=True),

        }

        rows.append(env)

    return rows


# --------------------------
# Save CSV
# --------------------------

def save_csv(rows):

    if not rows:
        return

    keys = rows[0].keys()

    with open("nxp_dataset.csv","w",newline="",encoding="utf8") as f:

        writer = csv.DictWriter(f,keys)

        writer.writeheader()

        writer.writerows(rows)

    print("\nSaved",len(rows),"rows to nxp_dataset.csv")


# --------------------------
# Main
# --------------------------

def run():

    rows = []

    categories = discover_categories()

    print("\nTotal categories discovered:",len(categories))

    product_pages = discover_product_pages(categories)

    print("\nTotal product pages discovered:",len(product_pages))

    for i,url in enumerate(product_pages):

        print(f"\nProcessing product {i+1}/{len(product_pages)}")

        try:

            html = fetch(url)

            prod = parse_product_page(html)

            print("Product Name:", prod["product_name"])
            print("Status:", prod["product_status"])
            print("Series:", prod["HIERARCHY_L4_SERIES"])

            pq = prod["package_quality_url"]

            if not pq:

                pq = url + "?tab=Package_Quality_Tab"

            pq_html = fetch(pq)

            env_rows = parse_env_table(pq_html)

            for env in env_rows:

                if len(rows) < 10:
                    print("Part:", env["PRODUCT_PART_NUMBER"],
                          "| Package:", env["PACKAGING_DESCR"],
                          "| ROHS:", env["EU_ROHS"])

                row = {}

                row.update(prod)

                row.update(env)

                row["PRODUCT_URL"] = url

                rows.append(row)

        except Exception as e:

            print("Failed product:", url)

            continue

        if i % 200 == 0:

            save_csv(rows)

        time.sleep(1)

    save_csv(rows)

    print("\nSCRAPING COMPLETE")
    print("TOTAL ROWS:", len(rows))


if __name__ == "__main__":

    run()