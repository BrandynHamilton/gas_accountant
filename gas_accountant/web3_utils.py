from web3 import Web3
from web3.exceptions import TransactionNotFound, TimeExhausted
from dotenv import load_dotenv
import os
import asyncio
from web3.exceptions import TransactionNotFound,TimeExhausted
import math
import traceback
import aiohttp
import datetime as dt
import pandas as pd

from gas_accountant.utils import convert_numpy

load_dotenv()

DEX_PORT = os.getenv('DEX_PORT')

API_KEY = os.getenv("APIKEY")
ACCOUNT_ADDRESS = os.getenv('DEX_ADDRESS')
PRIVATE_KEY = os.getenv('DEX_KEY')

GATEWAY_URL = os.getenv('GATEWAY_URL')
SEPOLIA_GATEWAY = os.getenv('SEPOLIA_GATEWAY')

TBTC_CONTRACT_ADDRESS = os.getenv('TEST_BTC')
TETH_CONTRACT_ADDRESS = os.getenv('TETH_WETH')

# Connect to Sepolia network
def network(chain='sepolia'):
    primary_gateway = GATEWAY_URL  # Infura URL
    backup_gateway = SEPOLIA_GATEWAY  # Backup gateway

    for gateway in [primary_gateway, backup_gateway]:
        w3 = Web3(Web3.HTTPProvider(gateway))
        if w3.is_connected():
            try:
                latest_block = w3.eth.get_block('latest')['number']  # Only try this if connected
                print(f"Connected to {chain} via {gateway}: {latest_block} block")
                return w3
            except Exception as e:
                print(f"Connected to {gateway} but failed to fetch latest block. Error: {e}")
        else:
            print(f"Failed to connect to {chain} via {gateway}. Trying next gateway...")

    raise ConnectionError(f"Failed to connect to {chain} network using both primary and backup gateways.")

def get_balance(w3, ACCOUNT_ADDRESS, TOKEN_CONTRACTS):
    """Fetch token balances using Web3."""
    try:
        # ERC20 ABI for balanceOf function
        erc20_abi = [
            {
                "constant": True,
                "inputs": [{"name": "_owner", "type": "address"}],
                "name": "balanceOf",
                "outputs": [{"name": "balance", "type": "uint256"}],
                "type": "function"
            }
        ]

        # Fetch balances programmatically
        balances = {}
        for token, address in TOKEN_CONTRACTS.items():
            if address:
                contract = w3.eth.contract(address=Web3.to_checksum_address(address), abi=erc20_abi)
                
                # Convert LocalAccount object to string if necessary
                account_address_str = ACCOUNT_ADDRESS.address if hasattr(ACCOUNT_ADDRESS, 'address') else str(ACCOUNT_ADDRESS)

                balance_wei = contract.functions.balanceOf(account_address_str).call()
                balances[token] = balance_wei / 10**18
            else:
                print(f"Contract address for {token} is not set.")

        # Print and return balances
        print(f"Balances for account {ACCOUNT_ADDRESS}: {balances}")
        return balances

    except Exception as e:
        print(f"Error fetching balances: {e}")
        return None

def get_contract_address(token):
    """Get contract address based on token name."""
    if token == 'TETH':
        return TETH_CONTRACT_ADDRESS
    elif token == 'TBTC':  
        return TBTC_CONTRACT_ADDRESS
    else:
        raise ValueError(f"Unknown token: {token}")

async def transfer_tokens(w3, account, token, amount, recipient_address):
    """Transfer tokens using Web3 with detailed debugging."""
    print(f"Starting transfer: token={token}, amount={amount}, recipient={recipient_address}")
    contract_address = get_contract_address(token)
    amount_wei = int(amount * 10**18)  # Adjust for token decimals

    # ERC20 ABI
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

    contract = w3.eth.contract(address=Web3.to_checksum_address(contract_address), abi=erc20_abi)
    nonce = w3.eth.get_transaction_count(ACCOUNT_ADDRESS, 'pending')

    print(f'nonce at dex_app transfer tokens: {nonce}')

    # Fetch initial gas price and gas limit estimation
    gas_price = max(w3.eth.gas_price, w3.to_wei('20', 'gwei'))
    try:
        estimated_gas = contract.functions.transfer(
            Web3.to_checksum_address(recipient_address), amount_wei
        ).estimate_gas({'from': account.address})
    except Exception as e:
        print(f"Gas estimation failed: {e}")
        return

    # Build the transaction
    tx = contract.functions.transfer(
        Web3.to_checksum_address(recipient_address),
        amount_wei
    ).build_transaction({
        'chainId': w3.eth.chain_id,
        'gas': estimated_gas,
        'gasPrice': gas_price,
        'nonce': nonce,
    })

    # Print transaction details
    print(f"Transaction details: {tx}")

    # Sign and send the transaction
    signed_tx = w3.eth.account.sign_transaction(tx, private_key=PRIVATE_KEY)
    print(f"Signed transaction hash: {signed_tx.hash.hex()}")

    try:
        tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        print(f"Transaction sent: {tx_hash.hex()}")
    except Exception as e:
        print(f"Error sending transaction: {e}")
        return

    # Wait for transaction confirmation
    try:
        receipt = await wait_for_transaction(w3, tx_hash)
        print(f"Transaction confirmed: {receipt}")
        return receipt
    except Exception as e:
        print(f"Transaction confirmation failed: {e}")
        return

async def wait_for_transaction(w3, tx_hash, retries=30, delay=60):
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

async def rebalance_fund_account(w3, account, prices, initial_holdings, new_compositions, recipient_address):
    """Rebalance fund account by transferring tokens."""
    print(f"Starting rebalance fund account...")
    print(f"Initial holdings: {initial_holdings}")
    print(f"Prices: {prices}")
    print(f"New compositions: {new_compositions}")

    # Fix: Directly use `prices[token]`
    total_value = sum(initial_holdings[token] * prices[token] for token in initial_holdings)

    print(f"Total portfolio value: {total_value}")

    # Fix: Calculate target balances correctly
    target_balances = {
        token: (total_value * new_compositions[token]) / prices[token]
        for token in new_compositions
    }
    
    print(f"Target balances: {target_balances}")

    # Calculate differences
    differences = {
        token: target_balances[token] - initial_holdings.get(token, 0) 
        for token in target_balances
    }
    print(f"Differences: {differences}")

    for token, difference in differences.items():
        print(f"Processing difference for {token}: {difference}")
        if difference > 0:
            print(f"Requesting {difference} of {token} from the fund to {recipient_address}...")
            await transfer_tokens(w3, account, token, difference, recipient_address)
        elif difference < 0:
            print(f"Skipping adjustment for {token}: {difference} (negative balance).")
        else:
            print(f"No adjustment needed for {token}.")


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

async def send_balances_to_fund(
    web3,
    account,
    initial_holdings: dict,
    target_balances: dict,
    prices: dict,
    new_compositions: dict,
    ACCOUNT_ADDRESS: str,
    FUND_ACCOUNT_ADDRESS: str
):
    """
    Compare current vs target balances, send any excess back on‐chain immediately,
    and bundle any deficits into a single rebalance request.
    """
    print("Starting send back balance function…")
    print("Current balances:", initial_holdings)
    print("Target balances:", target_balances)

    processed_tokens = set()
    needs_rebalance = False

    for token, target_balance in target_balances.items():
        if token in processed_tokens:
            print(f"Token {token} already processed. Skipping…")
            continue
        processed_tokens.add(token)

        current_balance = initial_holdings.get(token, 0)
        print(f"Token: {token}, current balance: {current_balance}")

        # diff > 0 → deficit, diff < 0 → excess
        diff = target_balance - current_balance
        diff = math.floor(diff * 10**6) / 10**6
        print(f"Token: {token}, clipped amount to adjust: {diff}")

        if math.isclose(diff, 0, abs_tol=1e-6):
            print(f"Skipping token {token} with negligible adjustment: {diff}")
            continue

        try:
            if diff < 0:
                # excess: send abs(diff) back on‐chain
                amount_to_send = abs(diff)
                print(f"Sending back {amount_to_send} of {token} to fund…")
                await transfer_tokens(
                    web3, account, token, amount_to_send, FUND_ACCOUNT_ADDRESS
                )
            else:
                # deficit: mark for grouped rebalance request
                print(f"Deficit of {diff} {token} detected, scheduling rebalance request…")
                needs_rebalance = True

        except Exception as e:
            print(f"Error processing token {token}: {e}")
            traceback.print_exc()

    if needs_rebalance:
        try:
            print("Sending rebalance request for deficits…")
            await send_rebalance_request(
                web3=web3,
                token=None,
                amount_to_send=None,
                recipient_address=ACCOUNT_ADDRESS,
                prices=prices,
                initial_holdings=initial_holdings,
                new_compositions=new_compositions
            )
        except Exception as e:
            print(f"Error during rebalance request: {e}")
            traceback.print_exc()

    print("Completed sending balances to fund.")


