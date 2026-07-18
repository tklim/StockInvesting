import json
import os
from datetime import date
from urllib.parse import urlencode

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

    if usage.get("date") != str(date.today()):
        return {"date": str(date.today()), "count": 0}

    return usage


def save_usage(usage):
    with open(USAGE_FILE, "w") as f:
        json.dump(usage, f, indent=2)


def safe_url(base_url, params):
    """Return request URL with API key hidden."""
    safe_params = params.copy()
    safe_params["apikey"] = "HIDDEN"
    return f"{base_url}?{urlencode(safe_params)}"


def summarize_global_quote(data):
    quote = data.get("Global Quote", {})

    if not quote:
        return

    print("\nGlobal Quote Summary")
    print("--------------------")
    print("Symbol:", quote.get("01. symbol"))
    print("Open:", quote.get("02. open"))
    print("High:", quote.get("03. high"))
    print("Low:", quote.get("04. low"))
    print("Price:", quote.get("05. price"))
    print("Volume:", quote.get("06. volume"))
    print("Latest trading day:", quote.get("07. latest trading day"))
    print("Previous close:", quote.get("08. previous close"))
    print("Change:", quote.get("09. change"))
    print("Change percent:", quote.get("10. change percent"))


def summarize_time_series(data):
    metadata = data.get("Meta Data")

    if metadata:
        print("\nMetadata")
        print("--------")
        for key, value in metadata.items():
            print(f"{key}: {value}")

    time_series_key = None

    for key in data.keys():
        if "Time Series" in key:
            time_series_key = key
            break

    if not time_series_key:
        return

    series = data[time_series_key]
    dates = list(series.keys())

    print(f"\nTime Series Summary: {time_series_key}")
    print("--------------------------------------")
    print("Number of data points returned:", len(dates))

    if dates:
        latest_date = dates[0]
        latest_data = series[latest_date]

        print("Latest date:", latest_date)
        print("Latest data:")
        for key, value in latest_data.items():
            print(f"  {key}: {value}")


def print_alpha_messages(data):
    message_keys = ["Note", "Information", "Error Message"]

    for key in message_keys:
        if key in data:
            print(f"\nAlpha Vantage {key}")
            print("-" * (15 + len(key)))
            print(data[key])


def alpha_request(params, preview_chars=1200):
    usage = load_usage()

    base_url = "https://www.alphavantage.co/query"
    request_params = params.copy()
    request_params["apikey"] = API_KEY

    print("\nRequest")
    print("-------")
    print(safe_url(base_url, request_params))

    try:
        response = requests.get(base_url, params=request_params, timeout=20)
        usage["count"] += 1
        save_usage(usage)

        print("\nHTTP Info")
        print("---------")
        print("Status code:", response.status_code)
        print("Content type:", response.headers.get("Content-Type"))
        print("Tracked calls today:", usage["count"])

        response.raise_for_status()
        data = response.json()

    except requests.exceptions.RequestException as e:
        print("\nRequest failed")
        print("--------------")
        print(e)
        return None

    except json.JSONDecodeError:
        print("\nResponse was not valid JSON")
        print("---------------------------")
        print(response.text[:preview_chars])
        return None

    print("\nResponse Overview")
    print("-----------------")
    print("Top-level keys:", list(data.keys()))

    print_alpha_messages(data)
    summarize_global_quote(data)
    summarize_time_series(data)

    print("\nRaw JSON Preview")
    print("----------------")
    print(json.dumps(data, indent=2)[:preview_chars])

    return data


# Example 1: Global quote
data = alpha_request({
    "function": "GLOBAL_QUOTE",
    "symbol": "IBM"
})

# Example 2: Daily time series
# data = alpha_request({
#     "function": "TIME_SERIES_DAILY",
#     "symbol": "IBM",
#     "outputsize": "compact"
# })
