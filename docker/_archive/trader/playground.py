import math


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
    daily_volatility = annual_volatility / math.sqrt(365)

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


# Example usage with the given data
current_price = 202.5
implied_volatility = 0.323340256
days_to_expiration = 21

result = calculate_standard_deviation_ranges(
    current_price,
    implied_volatility,
    days_to_expiration
)

print("Options Standard Deviation Ranges:")
print(f"Current Price: ${result['current_price']:.2f}")
print("\nFirst Standard Deviation:")
print(f"Lower Bound: ${result['first_std_dev']['lower']:.2f}")
print(f"Upper Bound: ${result['first_std_dev']['upper']:.2f}")
print("\nSecond Standard Deviation:")
print(f"Lower Bound: ${result['second_std_dev']['lower']:.2f}")
print(f"Upper Bound: ${result['second_std_dev']['upper']:.2f}")