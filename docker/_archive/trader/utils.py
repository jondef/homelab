import json
import math

import websockets


async def open_websocket_connection(dxlink_url: str, dx_link_token: str, symbol: str, period: str, from_time: int):
    """Opens a WebSocket connection to the specified DXLink URL and retrieves financial data.

    Args:
        dxlink_url (str): The URL of the DXLink server.
        dx_link_token (str): The authentication token for accessing the DXLink server.
        symbol (str): The symbol of the financial instrument.
        period (str): The period of the financial data (e.g., '1m', '1h', '1d').
        from_time (int): The starting timestamp (in seconds) for retrieving the financial data.

    Returns:
        list: A list of financial data objects.

    """
    data = []
    formatted_symbol = f"{symbol}{{={period}}}"
    from_time = from_time * 1000 # Convert to milliseconds
    count = 0

    async with (websockets.connect(dxlink_url) as ws):

        await ws.send(json.dumps({
          "type": "SETUP",
          "channel": 0,
          "acceptDataFormat": "COMPACT",
          "keepaliveTimeout": 30,
          "acceptKeepaliveTimeout": 30,
          "version": "0.1"
        }))

        await ws.send(json.dumps({"type": "AUTH", "token": dx_link_token, "channel": 0}))

        # Request a new channel for Quote events
        await ws.send(json.dumps({
            "type": "CHANNEL_REQUEST",
            "channel": 1,
            "service": "FEED",
            "parameters": {"contract": "AUTO"}
        }))

        # Subscribe to Candle events with time
        await ws.send(json.dumps({
          "type": "FEED_SUBSCRIPTION",
          "channel": 1,
          "add": [{ "symbol": formatted_symbol, "type": "Candle", "fromTime": from_time }]
        }))

        # Subscribe to Quote events
        if False: await ws.send(json.dumps({
            "type": "FEED_SUBSCRIPTION",
            "channel": 1,
            "add": [{"symbol": "AAPL", "type": "Quote"}]
        }))

        # Close channel
        if False: await ws.send(json.dumps({
          "type": "CHANNEL_CANCEL",
          "channel": 1
        }))

        # Handling received messages
        async for message in ws:
            #print("Received Message:")
            #print(message)
            payload = json.loads(message)

            if payload["type"] == "FEED_CONFIG":
                data.append(payload["eventFields"])

            if payload["type"] == "FEED_DATA":
                await ws.close()
                data.extend(payload["data"])
                return data

            if payload["type"] == "KEEPALIVE":
                if count > 5:
                    await ws.send(json.dumps({
                        "type": "KEEPALIVE",
                        "channel": 0
                    }))
                    count += 1

    return data


def calculate_standard_deviation_ranges(current_price, implied_volatility, days_to_expiration):
    """
    Calculate standard deviation ranges for an option based on implied volatility.

    :param current_price: Current stock price
    :param implied_volatility: Implied volatility as a decimal
    :param days_to_expiration: Number of days until option expiration
    :return: Dictionary of standard deviation ranges
    """
    # Annualize the volatility (assuming 252 trading days in a year)
    annual_volatility = implied_volatility

    # Calculate daily volatility
    daily_volatility = annual_volatility / math.sqrt(252)

    # Adjust volatility for specific time to expiration
    time_volatility = daily_volatility * math.sqrt(days_to_expiration)

    # Calculate standard deviation ranges
    first_std_dev_lower = current_price * (1 - time_volatility)
    first_std_dev_upper = current_price * (1 + time_volatility)

    second_std_dev_lower = current_price * (1 - (2 * time_volatility))
    second_std_dev_upper = current_price * (1 + (2 * time_volatility))

    return {
        "current_price": current_price,
        "first_std_dev": {
            "lower": first_std_dev_lower,
            "upper": first_std_dev_upper
        },
        "second_std_dev": {
            "lower": second_std_dev_lower,
            "upper": second_std_dev_upper
        }
    }
