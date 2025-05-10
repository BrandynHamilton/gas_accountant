import os
import json
import asyncio
import traceback
from flask import Flask, request, jsonify
from eth_account import Account
from web3 import Web3
from web3.exceptions import TransactionNotFound, TimeExhausted
from dotenv import load_dotenv
import pandas as pd
from functools import wraps

from gas_accountant import (network,rebalance_fund_account)

# Load environment variables
load_dotenv()

DEX_PORT = os.getenv('DEX_PORT')

API_KEY = os.getenv("APIKEY")
ACCOUNT_ADDRESS = os.getenv('DEX_ADDRESS')
PRIVATE_KEY = os.getenv('DEX_KEY')

GATEWAY_URL = os.getenv('GATEWAY_URL')
SEPOLIA_GATEWAY = os.getenv('SEPOLIA_GATEWAY')

TBTC_CONTRACT_ADDRESS = os.getenv('TEST_BTC')
TETH_CONTRACT_ADDRESS = os.getenv('TETH_WETH')

def require_api_key(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Extract API key from the request headers
        api_key = request.headers.get('x-api-key')
        if not api_key or api_key != API_KEY:
            return jsonify({"status": "error", "message": "Unauthorized. Invalid or missing API key."}), 401
        return f(*args, **kwargs)
    return decorated_function

w3 = network('sepolia')

# Setup account
account = Account.from_key(PRIVATE_KEY)
w3.eth.default_account = account.address

print(f"Connected account: {account.address}")

# Flask App
app = Flask(__name__)

@app.route('/rebalance', methods=['POST'])
async def rebalance():
    """Rebalance endpoint."""
    print(f"Received request: {request.data}")
    try:
        if not request.json:
            return jsonify({"status": "error", "message": "Invalid JSON payload"}), 400

        required_keys = ['recipient_address', 'prices', 'initial_holdings', 'new_compositions']
        for key in required_keys:
            if key not in request.json:
                return jsonify({"status": "error", f"message": "Missing key: {key}"}), 400

        data = request.json
        print(f"Parsed JSON: {data}")

        recipient_address = data['recipient_address']
        prices = data['prices']
        initial_holdings = data['initial_holdings']
        new_compositions = data['new_compositions']

        print(f"Recipient address: {recipient_address}")
        print(f"Prices: {prices}")
        print(f"Initial holdings: {initial_holdings}")
        print(f"New compositions: {new_compositions}")

        # Run the rebalance logic asynchronously
        await rebalance_fund_account(w3, account, prices, initial_holdings, new_compositions, recipient_address)

        return jsonify({"status": "success"})
    except KeyError as e:
        print(f"Missing key in input data: {e}")
        return jsonify({"status": "error", "message": f"Missing key: {str(e)}"}), 400
    except Exception as e:
        print(f"Error in rebalance: {e}")
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/', methods=['GET'])
def home():
    return jsonify({"message": "Welcome to the DEX App!"})

if __name__ == "__main__":
    app.run(port=DEX_PORT)
