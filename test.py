import requests
import json

# IG API credentials
API_KEY = "6f17bcadc89fac93cbde9f68198083692901f0c2"
USERNAME = "mailbox_sm"
PASSWORD = "Kenilworth123"
API_URL = "https://demo-api.ig.com/gateway/deal"  # Demo hesabı için
# API_URL = "https://api.ig.com/gateway/deal"     # Gerçek hesap için (canlı)

# Login function
def login(api_key, username, password):
    headers = {
        "X-IG-API-KEY": api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Version": "2"
    }
    data = {
        "identifier": username,
        "password": password
    }
    url = f"{API_URL}/session"
    response = requests.post(url, headers=headers, data=json.dumps(data))
    response.raise_for_status()
    resp_data = response.json()
    cst = response.headers.get("CST")
    x_security_token = response.headers.get("X-SECURITY-TOKEN")
    return cst, x_security_token

# Search function
def search_epic(ticker, cst, x_security_token, api_key):
    headers = {
        "X-IG-API-KEY": api_key,
        "CST": cst,
        "X-SECURITY-TOKEN": x_security_token,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Version": "1"
    }
    params = {
        "searchTerm": ticker
    }
    url = f"{API_URL}/markets"
    response = requests.get(f"{API_URL}/markets?searchTerm={ticker}", headers=headers)
    response.raise_for_status()
    return response.json()

# Main process
if __name__ == "__main__":
    # 1. Giriş yap
    cst, x_security_token = login(API_KEY, USERNAME, PASSWORD)

    # 2. Aranacak sembol
    ticker_to_search = "URW"

    # 3. EPIC arama
    results = search_epic(ticker_to_search, cst, x_security_token, API_KEY)

        # 4. Sonuçları yazdır
    for market in results['markets']:
        print(f"Name: {market['instrumentName']}")
        print(f"EPIC: {market['epic']}")
        print(f"Expiry: {market['expiry']}")
        print(f"------")
