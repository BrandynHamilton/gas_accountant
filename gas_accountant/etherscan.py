import requests
import pandas as pd
import datetime as dt
import numpy as np

def process_transaction(tx):
    gas_price = float(tx.get("gasPrice", np.nan))  # Allow gasPrice to be NaN
    gas_used = int(tx["gasUsed"])
    
    return {
        "blockNumber": int(tx["blockNumber"]),
        "timestamp": dt.datetime.utcfromtimestamp(int(tx["timeStamp"])),
        "transaction_hash": tx["hash"],
        "from": tx["from"],
        "to": tx["to"] if tx.get("to") else "Contract Deployment",
        "gas": int(tx["gas"]),
        "gasPrice": gas_price,  # Leave NaN if missing
        "gasUsed": gas_used,
        "tx_fee": (gas_used * gas_price / 1e18) if not np.isnan(gas_price) else np.nan,  # Handle NaN in calculation
        "contractAddress": tx.get("contractAddress"),  # Default to None if contractAddress is missing
    }

def get_tx_and_log_with_pagination(contract_address, start_block, end_block, etherscan_api_key,module='account',action='txlist'):
    """
    Fetch logs for a contract address with pagination support from the Etherscan API.

    Parameters:
        contract_address (str): The contract address to fetch logs for.
        start_block (int): The starting block number.
        end_block (int): The ending block number or "latest".
        etherscan_api_key (str): Your Etherscan API key.
        topic_filters (dict, optional): A dictionary of topic filters, e.g.,
            {
                "topic0": "0xe085b50dde9f45e2f6290b8f6eadc05e9f66d77b30d750cb3930c5e3430b9c1e",
                "topic1": "0x0000000000000000000000002102240d1a36a9dc9f3a4d07ee9251cb723aca89",
                "topic2": None,
                "topic3": None,
                "topic0_1_opr": "and"
            }

    Returns:
        list: A list of logs fetched from the API.
    """
    if module == 'account':
        data_pulled = 'tx'
    else:
        data_pulled = 'log'

    base_url = "https://api-sepolia.etherscan.io/api"
    logs = []  # To store all logs
    page = 1
    offset = 1000  # Max records per page

    print(f'getting fresh data')

    while True:
        # Construct the base URL
        url = (
            f"{base_url}?module={module}"
            f"&action={action}"
            f"&address={contract_address}"
            f"&fromBlock={start_block}"
            f"&toBlock={end_block}"
            f"&page={page}"
            f"&offset={offset}"
            f"&apikey={etherscan_api_key}"
        )

        try:
            # Make the API request
            response = requests.get(url)
            response.raise_for_status()

            data = response.json()
            print(data)
            if data["status"] != "1":  # Etherscan returns "1" for success
                print(f"No more {data_pulled}s or error: {data.get('message', 'Unknown error')}")
                break

            logs.extend(data["result"])  # Append the logs to the list
            print(f"Fetched {len(data['result'])} {data_pulled}s from page {page}.")

            # Stop if fewer than `offset` logs are returned
            if len(data["result"]) < offset:
                print(f"All {data_pulled}s fetched.")
                break

            page += 1  # Move to the next page

        except requests.RequestException as e:
            print(f"Error while fetching {data_pulled}s: {e}")
            break

    return logs

def parse_gas_log(log):
    """
    Parse a gas request log entry.

    Parameters:
        log (dict): A raw log entry from Etherscan.

    Returns:
        dict: Parsed log data.
    """
    # Extract transaction hash
    tx_hash = log["transactionHash"]

    # Extract requester's address from topic[1]
    requester = "0x" + log["topics"][1][-40:]

    # Decode data fields
    data = log["data"][2:]  # Remove "0x"
    timestamp = int(data[0:64], 16)  # Convert hex to int
    amount = int(data[64:128], 16) / 1e18  # Convert to ETH

    # Convert timestamp to human-readable format
    timestamp_human = dt.datetime.utcfromtimestamp(timestamp)

    return {
        "timestamp": timestamp_human,
        "transaction_hash": tx_hash,
        "requester": requester,
        "gas_amount_eth": amount,
    }

def get_eth_balances(api_key, addresses):
    """
    Fetch balances for multiple Ethereum addresses from Etherscan (Sepolia).
    
    :param api_key: Your Etherscan API key as a string.
    :param addresses: A list of Ethereum addresses.
    :return: JSON response with balances.
    """
    base_url = "https://api-sepolia.etherscan.io/api"
    
    # Convert list of addresses to comma-separated string
    addresses_str = ",".join(addresses)
    
    # Construct the API request URL
    params = {
        "module": "account",
        "action": "balancemulti",
        "address": addresses_str,
        "tag": "latest",
        "apikey": api_key
    }
    
    # Make the request
    response = requests.get(base_url, params=params)
    
    # Return the JSON response
    return response.json()