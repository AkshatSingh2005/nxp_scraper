import requests
import pandas as pd
import time

from dotenv import load_dotenv
import os

load_dotenv()

API_KEY = os.getenv("API_KEY")

url = f"https://api.mouser.com/api/v1/search/keyword?apiKey={API_KEY}"
headers = {"Content-Type": "application/json"}

companies = [
    "NXP",
    "Texas Instruments",
    "Infineon"
]

keywords = [
    "microcontroller","sensor","power","rf","processor",
    "amplifier","transceiver","converter","regulator",
    "mosfet","driver","controller"
]

all_products = []
seen_parts = set()

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

            response = requests.post(url, json=payload, headers=headers)
            data = response.json()

            parts = data.get("SearchResults", {}).get("Parts", [])

            if not parts:
                break

            for part in parts:

                part_number = part.get("ManufacturerPartNumber")

                if part_number in seen_parts:
                    continue

                seen_parts.add(part_number)

                row = {}

                # flatten basic attributes
                for k, v in part.items():
                    if isinstance(v, list) or isinstance(v, dict):
                        row[k] = str(v)
                    else:
                        row[k] = v

                all_products.append(row)

            print("Collected:", len(all_products))

            time.sleep(0.4)


df = pd.DataFrame(all_products)

df.to_csv("semiconductor_full_dataset.csv", index=False)

print("Dataset saved")
print("Total records:", len(df))