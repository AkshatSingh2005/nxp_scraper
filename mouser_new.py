import requests
import pandas as pd
import time



url = f"https://api.mouser.com/api/v1/search/keyword?apiKey={API_KEY}"
headers = {"Content-Type": "application/json"}

companies = [
    "NXP",
    "Texas Instruments",
    "Infineon",
    "STMicroelectronics",
    "Taiwan Semiconductor",
    "Taigo Yugen"
]

keywords = [
    "radio","rfid","nfc","npu"
]

all_products = []
seen = set()

for company in companies:

    for kw in keywords:

        query = f"{company} {kw}"
        print("Searching:", query)

        for start in range(0, 1000, 50):

            payload = {
                "SearchByKeywordRequest": {
                    "keyword": query,
                    "records": 50,
                    "startingRecord": start
                }
            }

            try:

                response = requests.post(url, json=payload, headers=headers)

                if response.status_code != 200:
                    print("Bad response:", response.status_code)
                    continue

                data = response.json()

            except Exception:
                print("Retrying request...")
                time.sleep(2)
                continue

            parts = data.get("SearchResults", {}).get("Parts", [])

            if not parts:
                break

            for part in parts:

                part_number = part.get("ManufacturerPartNumber")

                if part_number in seen:
                    continue

                seen.add(part_number)

                # price breaks
                price1 = price2 = price3 = price4 = ""

                price_breaks = part.get("PriceBreaks", [])

                if len(price_breaks) > 0:
                    price1 = f'{price_breaks[0]["Quantity"]}:{price_breaks[0]["Price"]}'
                if len(price_breaks) > 1:
                    price2 = f'{price_breaks[1]["Quantity"]}:{price_breaks[1]["Price"]}'
                if len(price_breaks) > 2:
                    price3 = f'{price_breaks[2]["Quantity"]}:{price_breaks[2]["Price"]}'
                if len(price_breaks) > 3:
                    price4 = f'{price_breaks[3]["Quantity"]}:{price_breaks[3]["Price"]}'

                all_products.append({

                    "Mouser Part Number": part.get("MouserPartNumber"),
                    "Manufacturer Part Number": part_number,
                    "Manufacturer Name": part.get("Manufacturer"),
                    "Availability": part.get("Availability"),
                    "Data Sheet URL": part.get("DataSheetUrl"),
                    "Part Description": part.get("Description"),
                    "Image URL": part.get("ImagePath"),
                    "Product Category": part.get("Category"),
                    "Packaging": part.get("Packaging"),
                    "Product Compliance": part.get("ProductCompliance"),
                    "Lifecycle Status": part.get("LifecycleStatus"),
                    "RoHS Status": part.get("ROHSStatus"),
                    "Reeling Availability": part.get("Reeling"),
                    "Minimum Order Quantity": part.get("Min"),
                    "Order Quantity Multiples": part.get("Mult"),
                    "Lead Time": part.get("LeadTime"),
                    "Suggested Replacement": part.get("SuggestedReplacement"),
                    "Product Detail Page URL": part.get("ProductDetailUrl"),
                    "Price Break 1": price1,
                    "Price Break 2": price2,
                    "Price Break 3": price3,
                    "Price Break 4": price4,
                    "Standard Pack Quantity": part.get("Mult")

                })

            print("Collected:", len(all_products))

            # SAVE PROGRESS EVERY 200 PRODUCTS
            if len(all_products) % 200 == 0:
                df = pd.DataFrame(all_products)
                df.to_csv("semiconductor_dataset_live.csv", index=False)
                print("Progress saved")

            time.sleep(1)


# FINAL SAVE
df = pd.DataFrame(all_products)
df.to_csv("semiconductor_dataset_final1.csv", index=False)

print("Finished")
print("Total parts collected:", len(df))