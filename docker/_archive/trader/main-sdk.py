from tastytrade_sdk import Tastytrade
import logging

# Set up logging configuration
logging.basicConfig(level=logging.DEBUG)  # This enables debug-level logging

tasty = Tastytrade(api_base_url = 'api.tastytrade.com')

tasty.login(
    login='defiljon',
    password='nR5x5pX9N6ruENM'
)

account_number = "5WW13756"

params = {
  "time-in-force": "Day",
  "order-type": "Limit",
  "price": 170,
  "price-effect": "Debit",
  "legs": [
    {
      "instrument-type": "Cryptocurrency",
      "symbol": "SOL/USD",
      "quantity": 1,
      "action": "Buy to Open"
    }
  ]
}



x = tasty.api.post(path = f"/accounts/{account_number}/orders", data = params)
print(x)
tasty.logout()