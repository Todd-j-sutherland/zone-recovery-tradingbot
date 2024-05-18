# Zone Recovery Trading Bot

## Overview
The Zone Recovery Trading Bot is an automated trading system designed to monitor and trade stocks using a combination of data from Alpaca and Interactive Brokers (IB). This bot employs a zone recovery strategy to manage trades and mitigate risks.

## Features
- **Automated Trading**: Executes trades based on predefined logic using data from Alpaca and IB.
- **Market Data Retrieval**: Fetches and processes market data to identify trading opportunities.
- **Zone Recovery Logic**: Implements a zone recovery strategy to manage trades effectively.
- **Multi-threading**: Uses threading to handle concurrent tasks such as fetching data and executing trades.
- **Configurable**: Allows users to specify stock tickers and set trading parameters.

## Prerequisites
- Python 3.7 or higher
- Accounts with Alpaca and Interactive Brokers
- API keys for Alpaca
- A running IB Gateway or TWS instance

## Installation
1. **Clone the repository**:
   ```sh
   git clone https://github.com/saibottrenham/zone-recovery-tradingbot.git
   cd zone-recovery-tradingbot
   ```

2. **Install required packages**:
   ```sh
   pip install -r requirements.txt
   ```

3. **Set up environment variables**:
   Create a `.env` file in the root directory with the following content:
   ```env
   TRADING_KEY=your_trading_api_key
   ALPACA_API_KEY=your_alpaca_api_key
   ALPACA_SECRET_KEY=your_alpaca_secret_key
   ALPACA_BASE_URL=https://paper-api.alpaca.markets
   ```

## Usage
1. **Start the IB Gateway or TWS**:
   Ensure that your IB Gateway or TWS is running and connected.

2. **Run the bot**:
   ```sh
   python bot.py AAPL MSFT TSLA
   ```
   Replace `AAPL MSFT TSLA` with the stock tickers you want to monitor and trade.

## Components

### IBClient
Handles the connection and communication with Interactive Brokers. Inherits from both `EWrapper` and `EClient` provided by the `ibapi` package.

### ZoneRecoveryBot
The core class that initializes the trading bot, fetches market data, and executes trades based on the zone recovery strategy.

### GetMarketData
A helper class to retrieve market data from various sources.

### ZoneRecoveryLogic
Implements the zone recovery trading logic.

## Configuration
- **tickers**: List of stock tickers to monitor and trade.
- **metadata_file**: JSON file to store metadata about the stocks.
- **data_update_interval**: Interval in seconds to fetch and update market data.

## Example Usage
```sh
python bot.py AAPL MSFT TSLA
```

## Logging
Logs are configured to output to the console with timestamp, log level, and message.

## Error Handling
- The bot is designed to handle common errors such as network issues and API request failures.
- Proper logging is implemented to capture and report errors.

## Contributing
Contributions are welcome! Please fork the repository and submit a pull request.

## License
This project is licensed under the MIT License. See the `LICENSE` file for details.
