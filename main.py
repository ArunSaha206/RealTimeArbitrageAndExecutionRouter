import os
from dotenv import load_dotenv
# 1. Import the correct, updated structures from the Webull SDK
from webull.core.client import ApiClient
from webull.data.data_client import DataClient
from webull.data.common.category import Category
from webull.data.common.timespan import Timespan

# Load keys from your hidden .env file
load_dotenv()

APP_KEY = os.environ.get("WEBULL_APP_KEY")
APP_SECRET = os.environ.get("WEBULL_APP_SECRET")
REGION = os.environ.get("WEBULL_REGION_ID")

print("Initializing Webull Data Client (Sandbox)...")

try:
    # 2. Build configuration baseline
    api_client = ApiClient(APP_KEY, APP_SECRET, REGION)
    
    # 3. Explicitly wire the client to use the UAT sandbox domain
    api_client.add_endpoint(REGION, "api.webull.com")
    
    # 4. Instantiate the official Data Client
    data_client = DataClient(api_client)
    
    print("Handshake successful! Fetching 1-minute historical bars for AAPL...")
    
    # 5. Grab the test historical bar data
    res = data_client.market_data.get_history_bar(
        "AAPL", 
        Category.US_STOCK.name, 
        Timespan.M1.name
    )
    
    if res.status_code == 200:
        print("\n Success! Data payload received:")
        print(res.json())
    else:
        print(f"\n Server returned status code {res.status_code}: {res.text}")

except Exception as e:
    print(f"\n Execution failed: {e}")