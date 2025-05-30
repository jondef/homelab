import requests

# region Balances and Positions
def get_account_balance(session_token, account_number):
    url = f"https://api.tastyworks.com/accounts/{account_number}/balances"
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'Authorization': session_token
    }

    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        balance_data = response.json()
        return balance_data
    else:
        raise Exception(f"Failed to retrieve account balance. Status code: {response.status_code}")
 

def get_balance_snapshots(session_token, account_number):
    url = f"https://api.tastyworks.com/accounts/{account_number}/balance-snapshots"
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'Authorization': session_token
    }

    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        balance_snapshots_data = response.json()
        return balance_snapshots_data
    else:
        raise Exception(f"Failed to retrieve balance snapshots. Status code: {response.status_code}")


def get_positions(session_token, account_number):
    base_url = "https://api.tastyworks.com"
    url = f"{base_url}/accounts/{account_number}/positions"
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'Authorization': session_token
    }

    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        positions_data = response.json()
        return positions_data
    else:
        raise Exception(f"Failed to retrieve positions. Status code: {response.status_code}")


# endregion

# region Accounts and Customers


def get_customer_info(session_token):
    base_url = "https://api.tastyworks.com"
    url = f"{base_url}/customers/me"
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'Authorization': session_token
    }

    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        customer_info = response.json()
        return customer_info
    else:
        raise Exception(f"Failed to retrieve customer information. Status code: {response.status_code}")


def get_customer_accounts(session_token):
    base_url = "https://api.tastyworks.com"
    url = f"{base_url}/customers/me/accounts"
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'Authorization': session_token
    }

    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        customer_accounts_data = response.json()
        return customer_accounts_data
    else:
        raise Exception(f"Failed to retrieve customer accounts. Status code: {response.status_code}")


def get_customer_account(session_token, account_number):
    base_url = "https://api.tastyworks.com"
    url = f"{base_url}/customers/me/accounts/{account_number}"
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'Authorization': session_token
    }

    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        customer_account_data = response.json()
        return customer_account_data
    else:
        raise Exception(f"Failed to retrieve customer account. Status code: {response.status_code}")


def get_quote_streamer_token(session_token):
    base_url = "https://api.tastyworks.com"
    url = f"{base_url}/quote-streamer-tokens"
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'Authorization': session_token
    }

    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        quote_streamer_data = response.json()
        return quote_streamer_data
    else:
        raise Exception(f"Failed to retrieve quote streamer token. Status code: {response.status_code}")


# endregion

# region Instruments

# Common headers for all requests
def get_headers(session_token: str):
    return {
        "User-Agent": "I love my dog",  # Python user agent doesn't work
        'Authorization': session_token,
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'Accept-Version': ''
    }


base_url = "https://api.tastyworks.com"


def make_request(session_token, url, params=None):
    response = requests.get(url, headers=get_headers(session_token), params=params)

    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"Request failed. Status code: {response.status_code}")


def get_cryptocurrencies(session_token):
    url = f"{base_url}/instruments/cryptocurrencies"
    return make_request(session_token, url)


def get_cryptocurrency_by_symbol(session_token, symbol="BTC/USD"):
    url = f"{base_url}/instruments/cryptocurrencies/{symbol}"
    return make_request(session_token, url)


def get_active_equities(session_token):
    url = f"{base_url}/instruments/equities/active"
    return make_request(session_token, url)


def get_equities(session_token, symbol="AAPL"):
    url = f"{base_url}/instruments/equities"
    params = {'symbol': symbol}
    return make_request(session_token, url, params)


def get_equity_by_symbol(session_token, symbol="AAPL"):
    url = f"{base_url}/instruments/equities/{symbol}"
    return make_request(session_token, url)


def get_equity_options(session_token):
    url = f"{base_url}/instruments/equity-options"
    return make_request(session_token, url)


def get_equity_option_by_symbol(session_token, symbol=None):
    url = f"{base_url}/instruments/equity-options/{symbol}"
    return make_request(session_token, url)


def get_futures(session_token):
    url = f"{base_url}/instruments/futures"
    return make_request(session_token, url)


def get_future_by_symbol(session_token, symbol=None):
    url = f"{base_url}/instruments/futures/{symbol}"
    return make_request(session_token, url)


def get_future_option_products(session_token):
    url = f"{base_url}/instruments/future-option-products"
    return make_request(session_token, url)


def get_future_option_product(session_token, exchange="CME", root_symbol="ES"):
    url = f"{base_url}/instruments/future-option-products/{exchange}/{root_symbol}"
    return make_request(session_token, url)


def get_future_products(session_token):
    url = f"{base_url}/instruments/future-products"
    return make_request(session_token, url)


def get_future_product(session_token, exchange="CME", code="ES"):
    url = f"{base_url}/instruments/future-products/{exchange}/{code}"
    return make_request(session_token, url)


def get_quantity_decimal_precisions(session_token):
    url = f"{base_url}/instruments/quantity-decimal-precisions"
    return make_request(session_token, url)


def get_warrants(session_token):
    url = f"{base_url}/instruments/warrants"
    return make_request(session_token, url)


def get_warrant_by_symbol(session_token, symbol=None):
    url = f"{base_url}/instruments/warrants/{symbol}"
    return make_request(session_token, url)


def get_future_option_chains_by_symbol(session_token, symbol="ES"):
    url = f"{base_url}/futures-option-chains/{symbol}"
    return make_request(session_token, url)


def get_future_option_chains_nested_by_symbol(session_token, symbol="CL"):
    url = f"{base_url}/futures-option-chains/{symbol}/nested"
    return make_request(session_token, url)


def get_option_chains_by_symbol(session_token, symbol):
    url = f"{base_url}/option-chains/{symbol}"
    return make_request(session_token, url)


def get_option_chains_nested_by_symbol(session_token, symbol="AAPL"):
    url = f"{base_url}/option-chains/{symbol}/nested"
    return make_request(session_token, url)


def get_option_chains_compact_by_symbol(session_token, symbol="AAPL"):
    url = f"{base_url}/option-chains/{symbol}/compact"
    return make_request(session_token, url)


# endregion

# region Orders

# Function to perform a Dry Run of an order
def order_dry_run(session_token, account_number, order_data):
    url = f"{base_url}/accounts/{account_number}/orders/dry-run"
    headers = get_headers(session_token)
    response = requests.post(url, headers=headers, json=order_data)
    return response.json()


# Function to place an Equity Order
def place_equity_order(session_token, account_number, order_data):
    url = f"{base_url}/accounts/{account_number}/orders"
    headers = get_headers(session_token)
    response = requests.post(url, headers=headers, json=order_data)
    return response.json()


# Function to get live orders
def get_live_orders(session_token, account_number):
    url = f"{base_url}/accounts/{account_number}/orders/live"
    headers = get_headers(session_token)
    response = requests.get(url, headers=headers)
    return response.json()


# Function to get all orders
def get_all_orders(session_token, account_number):
    url = f"{base_url}/accounts/{account_number}/orders"
    headers = get_headers(session_token)
    response = requests.get(url, headers=headers)
    return response.json()


# Function to get an order by its ID
def get_order_by_id(session_token, account_number, order_id):
    url = f"{base_url}/accounts/{account_number}/orders/{order_id}"
    headers = get_headers(session_token)
    response = requests.get(url, headers=headers)
    return response.json()


# Function to cancel an order
def cancel_order(session_token, account_number, order_id):
    url = f"{base_url}/accounts/{account_number}/orders/{order_id}"
    headers = get_headers(session_token)
    response = requests.delete(url, headers=headers)
    return response.json()


# Function to replace an order
def replace_order(session_token, account_number, order_id, new_order_data):
    url = f"{base_url}/accounts/{account_number}/orders/{order_id}"
    headers = get_headers(session_token)
    response = requests.put(url, headers=headers, json=new_order_data)
    return response.json()


# Function to edit an order
def edit_order(session_token, account_number, order_id, updated_order_data):
    url = f"{base_url}/accounts/{account_number}/orders/{order_id}"
    headers = get_headers(session_token)
    response = requests.patch(url, headers=headers, json=updated_order_data)
    return response.json()


# Function to edit an order with Dry Run
def edit_order_dry_run(session_token, account_number, order_id, updated_order_data):
    url = f"{base_url}/accounts/{account_number}/orders/{order_id}/dry-run"
    headers = get_headers(session_token)
    response = requests.post(url, headers=headers, json=updated_order_data)
    return response.json()


# endregion

# region Search for Symbols

# Function to search for a symbol
def search_for_symbol(session_token, symbol):
    url = f"{base_url}/symbols/search/{symbol}"
    headers = get_headers(session_token)
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"Symbol search failed. Status code: {response.status_code}")


# endregion

# region Transactions

# Function to get account transactions
def get_account_transactions(session_token, account_number):
    url = f"{base_url}/accounts/{account_number}/transactions"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": session_token
    }
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"Account transactions request failed. Status code: {response.status_code}")


# Function to get account transaction by ID
def get_account_transaction_by_id(session_token, account_number, transaction_id):
    url = f"{base_url}/accounts/{account_number}/transactions/{transaction_id}"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": session_token
    }
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"Account transaction by ID request failed. Status code: {response.status_code}")


# Function to get total transaction fees for an account
def get_total_transaction_fees(session_token, account_number):
    url = f"{base_url}/accounts/{account_number}/transactions/total-fees"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": session_token
    }
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"Total transaction fees request failed. Status code: {response.status_code}")


# endregion

# region Net Liq History

# Function to get Net Liquidating Value History
def get_net_liquidating_value_history(session_token, account_number):
    url = f"{base_url}/accounts/{account_number}/net-liq/history"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": session_token
    }
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"Net Liquidating Value History request failed. Status code: {response.status_code}")


# endregion

# region Market Metrics

# Function to get Volatility Data
def get_volatility_data(session_token, symbols: list):
    url = f"{base_url}/market-metrics?symbols={','.join(symbols)}"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": session_token
    }
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"Volatility Data request failed. Status code: {response.status_code}")


# Function to get Dividend History
def get_dividend_history(session_token, symbol):
    url = f"{base_url}/market-metrics/historic-corporate-events/dividends/{symbol}"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": session_token
    }
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"Dividend History request failed. Status code: {response.status_code}")


# Function to get Earnings Report History
def get_earnings_report_history(session_token, symbol):
    url = f"{base_url}/market-metrics/historic-corporate-events/earnings-reports/{symbol}"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": session_token
    }
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"Earnings Report History request failed. Status code: {response.status_code}")


# endregion





