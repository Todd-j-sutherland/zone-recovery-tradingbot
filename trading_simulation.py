import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from zone_recovery_logic import ZoneRecoveryLogic

def simulate_stock_price(days, initial_price=100, volatility=1):
    """ Generate a synthetic stock price series based on random walk theory. """
    prices = [initial_price]
    for _ in range(1, days):
        prices.append(prices[-1] * (1 + np.random.normal(0, volatility)))
    return prices

def run_simulation(days=250, initial_price=100):
    stock_prices = simulate_stock_price(days, initial_price)
    trading_bot = ZoneRecoveryLogic()
    stock_data = {'long': [], 'short': [], 'prices': []}

    results = []
    for current_price in stock_prices:
        stock_data['prices'].append(current_price)  # Update prices data for RSI calculation
        result = trading_bot.calculate_rsi_and_check_profit(stock_data, 'SYNTH', current_price)
        if result:
            action, price, profit = result
            if action == "CLOSE_ALL":
                results.append(profit)
                stock_data = {'long': [], 'short': [], 'prices': []}  # reset positions and prices
            elif action in ["BUY", "SELL"]:
                if action == "BUY":
                    stock_data['long'].append({'price': current_price, 'qty': 1})
                else:
                    stock_data['short'].append({'price': current_price, 'qty': 1})

    return results

# Run the simulation 100 times and calculate the average profit
num_runs = 1000
all_profits = []
for _ in range(num_runs):
    profits = run_simulation()
    all_profits.extend(profits)

if all_profits:
    average_profit = np.mean(all_profits)
    print(f"Average Profit over {num_runs} Simulated Periods: {average_profit:.2f}%")
    plt.plot(all_profits)
    plt.title('Profit per Trade Across All Simulations')
    plt.xlabel('Trade Number')
    plt.ylabel('Profit (%)')
    plt.show()
else:
    print("No trades were executed during any of the simulations.")


