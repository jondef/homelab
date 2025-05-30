
import time
import os
import asyncio
from datetime import datetime

from dotenv import load_dotenv
from API import *
from sessions import TastyworksSession
import pandas as pd
from utils import calculate_standard_deviation_ranges, open_websocket_connection

load_dotenv()


def execute_trade(session, subject, body):

    symbol = "AMZN"

    with TastyworksSession(os.environ.get("TT_USERNAME"), os.environ.get("TT_PASSWORD")) as session:
        print(get_account_balance(session, "5WW13756"))
        exit(0)

        # get current price
        dxlink_conn_info = get_quote_streamer_token(session["session-token"])
        data = asyncio.run(open_websocket_connection(dxlink_conn_info["data"]["dxlink-url"], dxlink_conn_info["data"]["token"], symbol, "1m", int(time.time() - 200)))
        price = [dict(zip(data[0]['Candle'], data[2][i:i + len(data[0]['Candle'])])) for i in range(0, len(data[2]), len(data[0]['Candle']))][0]["close"]


        option_chain = get_option_chains_by_symbol(session["session-token"], symbol)
        option_chain_eom = [option for option in option_chain["data"]["items"] if option.get("expiration-type") == "Regular"]

        option_expiration_dates = get_volatility_data(session["session-token"], [symbol])
        valid_expirations = {entry["expiration-date"] for entry in option_chain_eom}
        iv_option_chain = option_expiration_dates["data"]["items"][0]["option-expiration-implied-volatilities"]
        iv_option_chain_eom = [option for option in iv_option_chain if option["expiration-date"] in valid_expirations]

        days_to_expiration = (datetime.strptime(iv_option_chain_eom[0]['expiration-date'], "%Y-%m-%d") - datetime.today()).days + 1
        iv = calculate_standard_deviation_ranges(price, float(iv_option_chain_eom[0]["implied-volatility"]), days_to_expiration)

        print(iv)




execute_trade(None, 'Alert: Trend Line Predictor [saltwater_is_epic] (No Stop Loss) (10, 0): Any alert() function call', 'Sell Signal')