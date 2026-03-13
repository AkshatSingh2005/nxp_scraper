import requests
import pandas as pd

API_KEY = "YOUR_API_KEY"

url = f"https://api.mouser.com/api/v1/search/keyword?apiKey=9e30cb55-d1ad-4be3-b67a-78a53bb3dc25"

payload = {
    "SearchByKeywordRequest": {
        "keyword": "NXP microcontroller",
        "records": 5,
        "startingRecord": 0
    }
}

headers = {"Content-Type": "application/json"}

response = requests.post(url, json=payload, headers=headers)
data = response.json()

products = []

for part in data["SearchResults"]["Parts"]:

    # Extract price breaks
    prices = []
    if part.get("PriceBreaks"):
        for p in part["PriceBreaks"]:
            prices.append(f'{p["Quantity"]}:{p["Price"]}')

    products.append({
        "Manufacturer": part.get("Manufacturer"),
        "ManufacturerPartNumber": part.get("ManufacturerPartNumber"),
        "MouserPartNumber": part.get("MouserPartNumber"),
        "Category": part.get("Category"),
        "Description": part.get("Description"),
        "Availability": part.get("Availability"),
        "LeadTime": part.get("LeadTime"),
        "LifecycleStatus": part.get("LifecycleStatus"),
        "RoHSStatus": part.get("ROHSStatus"),
        "DatasheetURL": part.get("DataSheetUrl"),
        "ImageURL": part.get("ImagePath"),
        "ProductURL": part.get("ProductDetailUrl"),
        "MinOrderQty": part.get("Min"),
        "UnitWeight": part.get("UnitWeightKg"),
        "Packaging": part.get("Packaging"),
        "PriceBreaks": ", ".join(prices)
    })

df = pd.DataFrame(products)

print(df)

# Save dataset
df.to_csv("mouser_api_sample.csv", index=False)