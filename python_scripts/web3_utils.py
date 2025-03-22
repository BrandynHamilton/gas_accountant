from web3 import Web3


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

    
# def get_balance(TOKEN_CONTRACTS,w3,ACCOUNT_ADDRESS):
#     """Fetch token balances using Web3."""
#     try:
#         # ERC20 ABI for balanceOf function
#         erc20_abi = [
#             {
#                 "constant": True,
#                 "inputs": [{"name": "_owner", "type": "address"}],
#                 "name": "balanceOf",
#                 "outputs": [{"name": "balance", "type": "uint256"}],
#                 "type": "function"
#             }
#         ]

#         # Fetch balances programmatically
#         balances = {}
#         for token, address in TOKEN_CONTRACTS.items():
#             if address:
#                 contract = w3.eth.contract(address=Web3.to_checksum_address(address), abi=erc20_abi)
#                 balance_wei = contract.functions.balanceOf(ACCOUNT_ADDRESS).call()
#                 balances[token] = balance_wei / 10**18
#             else:
#                 print(f"Contract address for {token} is not set.")

#         # Print and return balances
#         print(f"Balances for account {ACCOUNT_ADDRESS}: {balances}")
#         return balances

#     except Exception as e:
#         print(f"Error fetching balances: {e}")
#         return None