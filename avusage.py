import json
import os
from datetime import date

import requests

API_KEY = os.environ.get("ALPHA_VANTAGE_API_KEY")
USAGE_FILE = "alphavantage_usage.json"

if not API_KEY:
    raise RuntimeError("Set ALPHA_VANTAGE_API_KEY before running this script.")


def load_usage():
    if not os.path.exists(USAGE_FILE):
        return {"date": str(date.today()), "count": 0}
    with open(USAGE_FILE, "r") as f:
        usage = json.load(f)
    if usage["date"] != str(date.today()):
        return {"date": str(date.today()), "count": 0}
    return usage


def save_usage(usage):
    with open(USAGE_FILE, "w") as f:
        json.dump(usage, f)


def alpha_request(params):
    usage = load_usage()

    url = "https://www.alphavantage.co/query"
    params["apikey"] = API_KEY

    r = requests.get(url, params=params, timeout=20)
    data = r.json()

    usage["count"] += 1
    save_usage(usage)

    if "Note" in data or "Information" in data:
        print("Alpha Vantage message:", data.get("Note") or data.get("Information"))
    else:
        print(f"Used {usage['count']} request(s) today.")

    return data


data = alpha_request({
    "function": "GLOBAL_QUOTE",
    "symbol": "IBM"
})
