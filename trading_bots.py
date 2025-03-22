# %%
from web3 import Web3
import os
from dotenv import load_dotenv
import pandas as pd
import prophet
import numpy as np
import datetime as dt
from datetime import timedelta
from prophet import Prophet
from eth_account import Account
from web3.middleware import geth_poa_middleware
from eth_abi import decode
from eth_utils import decode_hex, to_text
from flask import Flask, request, jsonify
from apscheduler.schedulers.background import BackgroundScheduler
from eth_account import Account

import requests
import random
import json

from dune_client.client import DuneClient

import plotly.graph_objs as go

# %%
load_dotenv()

ETHERSCAN_KEY = os.getenv("ETHERSCAN_KEY")
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY")
DUNE_API_KEY = os.getenv('DUNE_API_KEY')
FLIPSIDE_API_KEY=os.getenv('FLIPSIDE_API_KEY')
dune = DuneClient(DUNE_API_KEY)

FUND_ACCOUNT_ADDRESS = os.getenv('DEX_ADDRESS')

GAS_RESERVE = os.getenv('GAS_RESERVE')
# ACCOUNT_ADDRESS = os.getenv("PROTOCOL_CONTROLLER")
# PRIVATE_KEY = os.getenv("PROTOCOL_CONTROLLER_KEY")
YIELD_FARM_ADDRESS = os.getenv("YIELD_FARM_ADDRESS")
STAKING_CONTRACT = os.getenv("STAKING_CONTRACT")
SEPOLIA_GATEWAY = os.getenv("SEPOLIA_GATEWAY")

BOT_1_ADDRESS=os.getenv("BOT_1_ADDRESS")
BOT_2_ADDRESS=os.getenv("BOT_2_ADDRESS")

BOT_1_KEY=os.getenv("BOT_1_KEY")
BOT_2_KEY=os.getenv("BOT_2_KEY")

TBTC_CONTRACT_ADDRESS = os.getenv('TEST_BTC')
TETH_CONTRACT_ADDRESS = os.getenv('TETH_WETH')

BOTS_PORT = os.getenv('BOTS_PORT')

# %%

api = False

# %%
from python_scripts.web3_utils import get_balance

# %%
abi_path = r'gas_accountant_contracts\contracts\artifacts'
abi_paths = []  # Assuming GAS_ACCOUNTANT_ABI_PATH is predefined

for file in os.listdir(abi_path):
    if file.endswith('.json') and "metadata" not in file:  # Exclude metadata files
        abi_paths.append(os.path.join(abi_path, file))  # Add full path

print(abi_paths)  # Debug: Check the final list

abis = {}

for path in abi_paths:
    filename = os.path.basename(path)  # Extract filename (e.g., "YieldVault.json")
    name = os.path.splitext(filename)[0]  # Remove .json extension (e.g., "YieldVault")

    with open(path, "r") as file:
        abis[name] = json.load(file)  # Use name as key

print(abis)  # Debug output

# %%

def get_contract_address(token):
    """Get contract address based on token name."""
    if token == 'TBTC':
        return TBTC_CONTRACT_ADDRESS
    elif token == 'TETH':
        return TETH_CONTRACT_ADDRESS
    else:
        raise ValueError(f"Unknown token: {token}")

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

def convert_to_usd(TOKEN_CONTRACTS, balances, prices):
        """
        Convert token balances to their USD equivalent using token prices.

        Parameters:
        - balances (dict): Dictionary of token balances.
        - prices (dict): Dictionary of token prices.

        Returns:
        - dict: Dictionary of token balances converted to USD.
        """
        # Convert token keys to upper case for consistency
        balances = {token: balance for token, balance in balances.items()}

        print(f'balances: {balances.keys()}')
        print(f'TOKEN_CONTRACTS.keys(): {TOKEN_CONTRACTS.keys()}')

        for token in TOKEN_CONTRACTS.keys():
            if f"{token}" not in prices:
                print(f"Missing price for token: {token}")

        usd_balances = {
            token: balances[token] * prices[f"{token}"]
            for token in TOKEN_CONTRACTS.keys()
            if f"{token}" in prices
        }
        return usd_balances

    # %%
def get_wallet_state(TOKEN_CONTRACTS, original_balances,prices):
    # Fetch original holdings dynamically based on TOKEN_CONTRACTS
    original_holdings = {
        token: float(original_balances[token])
        for token in TOKEN_CONTRACTS.keys() if token in original_balances
    }

    print(f'initial prices for USD conversion: {prices}')
    print(f'initial balances used for USD conversion: {original_holdings}')

    # Convert balances to USD
    balances_in_usd = convert_to_usd(TOKEN_CONTRACTS, original_holdings, prices)
    initial_portfolio_balance = sum(balances_in_usd.values())

    # Calculate compositions dynamically
    print(f'balances_in_usd.items(): {balances_in_usd.items()}')

    comp_dict = {
        f"{token} comp": balance_usd / initial_portfolio_balance
        for token, balance_usd in balances_in_usd.items()
    }

    today_utc = dt.datetime.now(dt.timezone.utc) 
    formatted_today_utc = today_utc.strftime('%Y-%m-%d %H:00:00')

    comp_dict["date"] = formatted_today_utc

    print(f'Composition dictionary: {comp_dict}')

    return comp_dict, balances_in_usd, initial_portfolio_balance

from web3.exceptions import TransactionNotFound,TimeExhausted
import asyncio
import math
import traceback
import aiohttp


# %%
async def wait_for_transaction(w3,tx_hash, retries=30, delay=60):
    """Wait for transaction confirmation with detailed debugging."""
    print(f"Waiting for transaction receipt: {tx_hash.hex()}")
    for attempt in range(retries):
        try:
            receipt = w3.eth.get_transaction_receipt(tx_hash)
            print(f"Transaction receipt: {receipt}")
            if receipt and receipt['status'] == 1:
                print(f"Transaction {tx_hash.hex()} confirmed successfully.")
                return receipt
            elif receipt and receipt['status'] == 0:
                raise Exception(f"Transaction {tx_hash.hex()} failed on-chain.")
        except TransactionNotFound:
            print(f"Transaction {tx_hash.hex()} not yet confirmed. Attempt {attempt + 1}/{retries}. Retrying...")
        except TimeExhausted:
            print("Transaction confirmation timed out.")
            break
        await asyncio.sleep(delay)
    raise Exception(f"Transaction {tx_hash.hex()} failed to confirm within {retries} attempts.")

# %%
async def transfer_tokens(w3_instance, private_key, token, amount, recipient_address):
    """Ensure the correct Web3 instance is used for transactions."""
    print(f"Starting transfer: token={token}, amount={amount}, recipient={recipient_address}")

    sender_address = Account.from_key(private_key).address
    print(f"Sender Address: {sender_address}")

    contract_address = get_contract_address(token)
    amount_wei = int(amount * 10**18)

    # ERC20 ABI
    erc20_abi = [
        {
            "constant": False,
            "inputs": [{"name": "_to", "type": "address"}, {"name": "_value", "type": "uint256"}],
            "name": "transfer",
            "outputs": [{"name": "", "type": "bool"}],
            "type": "function"
        }
    ]

    contract = w3_instance.eth.contract(address=Web3.to_checksum_address(contract_address), abi=erc20_abi)

    # ✅ Get latest nonce (fixes "nonce too low" issue)
    nonce = w3_instance.eth.get_transaction_count(sender_address, "pending")
    print(f"Using nonce: {nonce}")

    # ✅ Fetch gas price
    gas_price = max(w3_instance.eth.gas_price, w3_instance.to_wei("20", "gwei"))

    # ✅ Estimate gas
    try:
        estimated_gas = contract.functions.transfer(
            Web3.to_checksum_address(recipient_address), amount_wei
        ).estimate_gas({'from': sender_address})
    except Exception as e:
        print(f"Gas estimation failed: {e}")
        return None

    # ✅ Build transaction
    tx = contract.functions.transfer(
        Web3.to_checksum_address(recipient_address),
        amount_wei
    ).build_transaction({
        'chainId': w3_instance.eth.chain_id,
        'gas': estimated_gas,
        'gasPrice': gas_price,
        'nonce': nonce,
    })

    print(f"Transaction details: {tx}")

    # ✅ Sign transaction
    signed_tx = w3_instance.eth.account.sign_transaction(tx, private_key=private_key)
    print(f"Signed transaction hash: {signed_tx.hash.hex()}")

    # ✅ Send transaction
    try:
        tx_hash = w3_instance.eth.send_raw_transaction(signed_tx.rawTransaction)
        print(f"Transaction sent: {tx_hash.hex()}")
        return tx_hash.hex()
    except Exception as e:
        print(f"Error sending transaction: {e}")
        return None


# %%
import json
import numpy as np
import aiohttp
import asyncio

def convert_numpy(obj):
        if isinstance(obj, np.integer):
            return int(obj)  # Convert np.int64 → int
        elif isinstance(obj, np.floating):
            return float(obj)  # Convert np.float64 → float
        elif isinstance(obj, dict):
            return {k: convert_numpy(v) for k, v in obj.items()}  # Convert dict values
        elif isinstance(obj, list):
            return [convert_numpy(i) for i in obj]  # Convert list elements
        return obj  # Return original if not NumPy type

async def send_rebalance_request(web3, token, amount_to_send, recipient_address, prices, initial_holdings, new_compositions):
    """Send rebalance request to the DEX app's endpoint."""
    url = 'http://127.0.0.1:5001/rebalance'

    # Convert all NumPy types to Python native types
    
    rebalance_data = {
        'recipient_address': web3.to_checksum_address(recipient_address),
        'prices': convert_numpy(prices),
        'initial_holdings': convert_numpy(initial_holdings),
        'new_compositions': convert_numpy(new_compositions)
    }

    print(f"Sending rebalance request to {url} with data: {rebalance_data}")

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=300)) as session:
            async with session.post(url, json=rebalance_data) as response:
                if response.status == 200:
                    print(f"Rebalance response: {await response.json()}")
                else:
                    print(f"Error: Received status {response.status} with response: {await response.text()}")
    except asyncio.TimeoutError:
        print(f"Timeout error when sending rebalance request for token: {token}")
    except aiohttp.ClientError as e:
        print(f"Error sending rebalance request: {e}, data: {rebalance_data}")


    # %%
async def send_balances_to_fund(web3, contract_abi, private_key, initial_holdings, target_balances, prices, new_compositions,ACCOUNT_ADDRESS):
    print(f"Starting send back balance function...")
    print("Current balances:", initial_holdings)
    print("Target balances:", target_balances)

    processed_tokens = set()
    needs_rebalance = False  # Track if we need to send a rebalance request

    for token, target_balance in target_balances.items():
        if token in processed_tokens:
            print(f"Token {token} already processed. Skipping...")
            continue

        processed_tokens.add(token)

        current_balance = initial_holdings.get(token, 0)
        print(f"Token: {token}, current balance: {current_balance}")
        amount_to_adjust = current_balance - target_balance
        amount_to_adjust = math.floor(amount_to_adjust * 10**6) / 10**6
        print(f"Token: {token}, clipped amount to adjust: {amount_to_adjust}")

        if math.isclose(amount_to_adjust, 0, abs_tol=1e-6):
            print(f"Skipping token {token} with negligible adjustment: {amount_to_adjust}")
            continue

        try:
            if amount_to_adjust > 0:
                # Handle excess tokens individually
                print(f"Sending back {amount_to_adjust} of {token} to the fund.")
                await transfer_tokens(web3,private_key,token=token, amount=amount_to_adjust, recipient_address=FUND_ACCOUNT_ADDRESS)
            elif amount_to_adjust < 0:
                # Mark that we need a rebalance request
                needs_rebalance = True
        except Exception as e:
            print(f"Error processing token {token}: {e}")
            traceback.print_exc()

    # If any token requires rebalance, send a single request for all tokens
    if needs_rebalance:
        try:
            await send_rebalance_request(
                web3=web3,
                token=None,  # Not used
                amount_to_send=None,  # Not used
                recipient_address=ACCOUNT_ADDRESS,
                prices=prices,
                initial_holdings=initial_holdings,
                new_compositions=new_compositions,
            )
        except Exception as e:
            print(f"Error during rebalance request: {e}")
            traceback.print_exc()

    print("Completed sending balances to fund.")

async def main(w3,PRIVATE_KEY):

# %%
    w3 = Web3(Web3.HTTPProvider(SEPOLIA_GATEWAY))

    ACCOUNT = Account.from_key(PRIVATE_KEY)

    w3.eth.default_account = ACCOUNT.address
    w3.middleware_onion.inject(geth_poa_middleware, layer=0)

    # %%
    print(f"✅ Web3 Connection Check: {w3.is_connected()}")
    print(f"✅ Using Account: {Account.from_key(PRIVATE_KEY).address}")
    print(f"✅ Next Nonce: {w3.eth.get_transaction_count(Account.from_key(PRIVATE_KEY).address, 'pending')}")

    # %%
    TOKEN_CONTRACTS = {'tbtc':TBTC_CONTRACT_ADDRESS,
                    'teth':TETH_CONTRACT_ADDRESS }
    TOKEN_CONTRACTS = {token.upper(): address for token, address in TOKEN_CONTRACTS.items()}

    # %%
    BOT_BALANCE  = get_balance(w3,ACCOUNT,TOKEN_CONTRACTS)
    print(f'original_balances: {BOT_BALANCE}')

    prices = {
        "TBTC":get_token_price('0x2260fac5e5542a773aa44fbcfedf7c193bc2c599'),
        'TETH':get_token_price()
    
    }
    # %%
    BOT_STATE = get_wallet_state(TOKEN_CONTRACTS,BOT_BALANCE,prices)

    # %%
    def normalize_portfolio(portfolio):
        total = np.sum(portfolio)
        if total == 0:
            # If the total is zero, avoid division by zero and return an equally distributed portfolio
            return np.ones_like(portfolio) / len(portfolio)
        return portfolio / total

    # %%
    BOT_PORTFOLIO_ACTION = np.random.rand(2)
    BOT_PORTFOLIO_ACTION = normalize_portfolio(BOT_PORTFOLIO_ACTION) 
    # %%
    BOT_ACTION_DF = pd.DataFrame(columns=['TETH','TBTC'],data=BOT_PORTFOLIO_ACTION.reshape(1, -1))
    BOT_ACTION_DF

    # %%
    # Get new compositions dynamically from model actions
    new_compositions = {
        token: float(BOT_ACTION_DF.iloc[-1][f"{token}"]) for token in TOKEN_CONTRACTS
    }

    print(f'new compositions: {new_compositions}')

    # Calculate total portfolio value
    total_value = sum(
        BOT_BALANCE[token] * prices[f"{token}"] for token in TOKEN_CONTRACTS
    )

    target_balances = {
        token: total_value * new_compositions.get(token, 0) / prices[f"{token}"]
        for token in TOKEN_CONTRACTS
    }

    # %%
    token_1_rebal_info = {
        "new compositions": new_compositions,
        "prices": prices,
        "initial holdings": BOT_BALANCE,
        "account address": ACCOUNT,
        "target balances": target_balances,
        **{
            f"{token} bal usd": BOT_BALANCE[token] * prices[f"{token}"]
            for token in TOKEN_CONTRACTS
        },
        "portfolio balance": total_value
    }


    # %%
    erc20_abi = [
        {
            "constant": False,
            "inputs": [
                {"name": "_to", "type": "address"},
                {"name": "_value", "type": "uint256"}
            ],
            "name": "transfer",
            "outputs": [{"name": "", "type": "bool"}],
            "type": "function"
        }
    ]

    # %%
    def get_contract_address(token):
        """Get contract address based on token name."""
        if token == 'TBTC':
            return TBTC_CONTRACT_ADDRESS
        elif token == 'TETH':
            return TETH_CONTRACT_ADDRESS
        else:
            raise ValueError(f"Unknown token: {token}")

    # %%

    # %%
    ACCOUNT_ADDRESS = Account.from_key(PRIVATE_KEY).address

    print(f"✅ Your account: {ACCOUNT_ADDRESS}")

    # Set default account
    W3_BOT1.eth.default_account = ACCOUNT_ADDRESS

    # %%
    print(f"DEBUG: Web3 Client Version: {w3.client_version}")  # ✅ CORRECT
    print(f"Web3 Instance Type: {type(w3)}")
    print(f"Web3 Connected: {w3.is_connected()}")
    print(f"Web3 Client Version: {getattr(w3, 'client_version', 'Not Available')}")
    print(f"Web3 Accounts: {w3.eth.accounts if w3.is_connected() else 'Not Connected'}")


    # %%
    await send_balances_to_fund(w3, erc20_abi, PRIVATE_KEY, BOT_BALANCE, target_balances, prices, new_compositions,ACCOUNT_ADDRESS)

    return {
        "new_compositions": new_compositions,
        "prices": prices,
        "initial_holdings": BOT_BALANCE,
        "target_balances": target_balances,
        "portfolio_balance": total_value,
    }

def run_async_main(w3, private_key):
    """Helper function to run async main inside a synchronous scheduler job."""
    asyncio.run(main(w3, private_key))

app = Flask(__name__)
scheduler = BackgroundScheduler()
scheduler.start()

SEPOLIA_GATEWAY = os.getenv("SEPOLIA_GATEWAY")
BOT_1_KEY = os.getenv("BOT_1_KEY")
BOT_2_KEY = os.getenv("BOT_2_KEY")

# Connect Bot 1
W3_BOT1 = Web3(Web3.HTTPProvider(SEPOLIA_GATEWAY))
ACCOUNT_BOT_1 = Account.from_key(BOT_1_KEY)
W3_BOT1.eth.default_account = ACCOUNT_BOT_1.address
W3_BOT1.middleware_onion.inject(geth_poa_middleware, layer=0)

# Connect Bot 2
W3_BOT2 = Web3(Web3.HTTPProvider(SEPOLIA_GATEWAY))
ACCOUNT_BOT_2 = Account.from_key(BOT_2_KEY)
W3_BOT2.eth.default_account = ACCOUNT_BOT_2.address
W3_BOT2.middleware_onion.inject(geth_poa_middleware, layer=0)

# Token Contracts
TBTC_CONTRACT_ADDRESS = os.getenv("TEST_BTC")
TETH_CONTRACT_ADDRESS = os.getenv("TETH_WETH")
TOKEN_CONTRACTS = {'TBTC': TBTC_CONTRACT_ADDRESS, 'TETH': TETH_CONTRACT_ADDRESS}

# Scheduled Tasks
scheduler.add_job(lambda: run_async_main(W3_BOT1, BOT_1_KEY), 'interval', hours=1)
scheduler.add_job(lambda: run_async_main(W3_BOT2, BOT_2_KEY), 'interval', hours=3)

# ✅ Flask API Endpoints (Fixed Async Handling)
@app.route('/')
def home():
    return jsonify({"message": "Trading Bots Running"})

@app.route('/bot1/status')
async def bot1_status():
    result = await main(W3_BOT1, BOT_1_KEY)
    return jsonify(convert_numpy(result))  # ✅ Apply conversion before returning JSON

@app.route('/bot2/status')
async def bot2_status():
    result = await main(W3_BOT2, BOT_2_KEY)
    return jsonify(convert_numpy(result))  # ✅ Apply conversion before returning JSON

@app.route('/bot1/rebalance', methods=['POST'])
async def trigger_bot1_rebalance():
    result = await main(W3_BOT1, BOT_1_KEY)
    return jsonify({"status": "success", "data": convert_numpy(result)})

@app.route('/bot2/rebalance', methods=['POST'])
async def trigger_bot2_rebalance():
    result = await main(W3_BOT2, BOT_2_KEY)
    return jsonify({"status": "success", "data": convert_numpy(result)})

@app.route('/rebalance/all', methods=['POST'])
async def trigger_all_rebalances():
    result1 = await main(W3_BOT1, BOT_1_KEY)
    result2 = await main(W3_BOT2, BOT_2_KEY)
    return jsonify({"status": "success", "data": {"bot1": convert_numpy(result1), "bot2": convert_numpy(result2)}})

if __name__ == "__main__":
    app.run(port=BOTS_PORT)

