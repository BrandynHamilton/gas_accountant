import requests
import pandas as pd
import os
from dune_client.client import DuneClient
import json

from dotenv import load_dotenv

load_dotenv()

COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY")
DUNE_API_KEY = os.getenv('DUNE_API_KEY')

dune = DuneClient(DUNE_API_KEY)

def get_token_price(token='0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2'):
    url = f"https://api.coingecko.com/api/v3/simple/token_price/ethereum?contract_addresses={token}&vs_currencies=usd"

    headers = {
        "accept": "application/json",
        "x-cg-demo-api-key": COINGECKO_API_KEY
    }

    response = requests.get(url, headers=headers)

    eth_data = response.json()

    eth_df = pd.DataFrame(eth_data)
    eth_usd = eth_df[f'{token}'].values[0]

    print(eth_usd)

    return eth_usd

def get_price_timeseries(token='ethereum',days='90'):

    url = f"https://api.coingecko.com/api/v3/coins/{token}/market_chart?vs_currency=usd&days={days}"

    headers = {
        "accept": "application/json",
        "x-cg-demo-api-key": COINGECKO_API_KEY
    }

    response = requests.get(url, headers=headers)
    response_text = response.text
    data = json.loads(response_text)
    df_prices = pd.DataFrame(data["prices"], columns=["timestamp", "price"])
    df_prices["timestamp"] = pd.to_datetime(df_prices["timestamp"], unit='ms')  # Convert to datetime
    df_prices.set_index('timestamp', inplace=True)

    # df_prices.index - pd.to_datetime(df_prices.index.strftime('%Y-%m-%d %H:00:00'))
    # df_prices = df_prices.resample('H').last()

    return df_prices

def dune_api_results(query_num, save_csv=False, csv_path=None):
    results = dune.get_latest_result(query_num)
    df = pd.DataFrame(results.result.rows)

    if save_csv and csv_path:
        df.to_csv(csv_path, index=False)
    return df

def flipside_api_results(query, api_key, attempts=10, delay=30):
    """
    Creates and retrieves results for a query using Flipside's JSON-RPC API with pagination.

    Parameters:
    - query: str, the SQL query to execute.
    - api_key: str, your Flipside API key.
    - attempts: int, number of attempts to poll for query completion.
    - delay: int, delay (in seconds) between polling attempts.

    Returns:
    - pd.DataFrame: DataFrame containing the query results.
    """
    import requests
    import time
    import pandas as pd

    # Step 1: Create the query
    url = "https://api-v2.flipsidecrypto.xyz/json-rpc"
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key
    }
    payload = {
        "jsonrpc": "2.0",
        "method": "createQueryRun",
        "params": [
            {
                "resultTTLHours": 1,
                "maxAgeMinutes": 0,
                "sql": query,
                "tags": {"source": "python-script", "env": "production"},
                "dataSource": "snowflake-default",
                "dataProvider": "flipside"
            }
        ],
        "id": 1
    }

    response = requests.post(url, headers=headers, json=payload)
    response_data = response.json()

    if 'error' in response_data:
        raise Exception(f"Error creating query: {response_data['error']['message']}")

    query_run_id = response_data.get('result', {}).get('queryRun', {}).get('id')
    if not query_run_id:
        raise KeyError(f"Query creation failed. Response: {response_data}")

    # Step 2: Poll for query completion
    for attempt in range(attempts):
        status_payload = {
            "jsonrpc": "2.0",
            "method": "getQueryRunResults",
            "params": [
                {
                    "queryRunId": query_run_id,
                    "format": "json",
                    "page": {"number": 1, "size": 10000}
                }
            ],
            "id": 1
        }
        response = requests.post(url, headers=headers, json=status_payload)
        resp_json = response.json()

        if 'result' in resp_json and 'rows' in resp_json['result']:
            # Step 3: Handle pagination
            all_rows = []
            page_number = 1

            while True:
                status_payload["params"][0]["page"]["number"] = page_number
                response = requests.post(url, headers=headers, json=status_payload)
                resp_json = response.json()

                if 'result' in resp_json and 'rows' in resp_json['result']:
                    rows = resp_json['result']['rows']
                    if not rows:
                        break  # No more rows to fetch
                    all_rows.extend(rows)
                    page_number += 1
                else:
                    break

            # Convert the rows to a DataFrame
            return pd.DataFrame(all_rows)

        if 'error' in resp_json and 'not yet completed' in resp_json['error'].get('message', '').lower():
            time.sleep(delay)  # Wait before retrying
        else:
            raise Exception(f"Unexpected error while fetching query results: {resp_json}")

    raise TimeoutError(f"Query did not complete after {attempts} attempts.")
