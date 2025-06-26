# crypto-trades-firefly-iii

**Import your crypto trading activity into Firefly III for unified personal finance tracking.**

---

## Project Summary

`crypto-trades-firefly-iii` is a service that automatically imports your trades, deposits, withdrawals, and interest from supported crypto trading platforms into your [Firefly III](https://firefly-iii.org/) instance. It helps you keep a complete and up-to-date overview of your crypto assets alongside your other finances.

**Who is this for?**

- Crypto traders and investors who use Firefly III for personal finance.
- Anyone who wants to automate the tracking of their crypto transactions and balances.

---

## Features ✨

- 🔄 **Automated Trade Import:** Syncs executed trades as transactions in Firefly III, including asset and currency movements.
- 💸 **Commission Tracking:** Imports paid fees as separate transactions, linked to the correct accounts.
- 💰 **Interest Handling:** Automatically imports received interest from savings, lending, or staking.
- 📥📤 **Deposits & Withdrawals:** Imports crypto deposits and withdrawals, with support for classifying transactions as transfers for supported blockchains.
- 🏷️ **Tagging & Notes:** All transactions are tagged and annotated for easy filtering and reporting in Firefly III.
- 🔗 **Multiple Exchange Support:** Can be run for multiple exchanges (recommended: one instance per exchange).
- 🐳 **Docker & Standalone:** Easy to run as a Docker container or as a standalone Python script.

---

## Big Picture

[Big Picture](plantuml/overview.svg)
<img src="plantuml/overview.svg">

---

## Quick Start 🚀

### Prerequisites

- Python 3.9 (if running standalone)
- Docker (if running as a container)
- A running Firefly III instance (tested with v5.4.6)
- API keys for your crypto exchange(s)
- Firefly III API access token

### Run with Docker (Recommended)

```sh
docker pull financelurker/crypto-trades-firefly-iii:latest
docker run --env ... financelurker/crypto-trades-firefly-iii:latest
```

### Run Standalone

```sh
git clone https://github.com/financelurker/crypto-trades-firefly-iii.git
cd crypto-trades-firefly-iii
python -m pip install --upgrade setuptools pip wheel
python -m pip install --upgrade pyyaml
python -m pip install Firefly-III-API-Client python-binance cryptocom-exchange
python main.py
```

---

## Configuration ⚙️

Set the following environment variables to configure the service:

| Variable               | Description                                                  | Type    | Required | Default |
| ---------------------- | ------------------------------------------------------------ | ------- | -------- | ------- |
| `FIREFLY_HOST`         | URL to your Firefly III instance                             | string  | Yes      |         |
| `FIREFLY_VALIDATE_SSL` | Enable/disable SSL certificate validation                    | boolean | No       | true    |
| `FIREFLY_ACCESS_TOKEN` | Firefly III API access token                                 | string  | Yes      |         |
| `SYNC_BEGIN_TIMESTAMP` | Earliest date for imported transactions (yyyy-MM-dd)         | date    | Yes      |         |
| `SYNC_TRADES_INTERVAL` | How often to sync: `hourly`, `daily`, or `debug` (every 10s) | enum    | Yes      |         |
| `DEBUG`                | Enable debug mode and add 'dev' tag to transactions          | boolean | No       | false   |

For exchange-specific configuration, see [supported exchanges](src/backends/exchanges/README.md#how-to-use-supported-exchanges).

---

## Imported Movements

### Executed Trades 💸

- Each trade creates asset/currency transactions in Firefly III.
- Paid commissions are imported as separate transactions.
- All transactions are tagged and annotated for easy filtering.

### Received Interest 💰

- Interest from savings/lending/staking is imported as revenue.

### Withdrawals & Deposits 📥📤

- Crypto deposits/withdrawals are imported and can be classified as transfers for supported blockchains.
- Unclassified transactions are tagged for later review.

### On-/Off-ramping (SEPA) 🏦

- Planned for future releases.

---

## Troubleshooting 🐞

- **No transactions imported?**
  - Check your environment variables, especially API keys and tokens.
  - Ensure your Firefly III instance is reachable and the access token is valid.
  - Make sure your exchange API keys have the necessary permissions.
- **SSL errors?**
  - Set `FIREFLY_VALIDATE_SSL=false` if using self-signed certificates.
- **Python errors about missing modules?**
  - Run the install commands in the Quick Start section.
- **Still stuck?**
  - Check the logs (enable `DEBUG` for more detail) or open an issue on GitHub.

---

## Contributing 🤝

Contributions are welcome! To get started:

1. Fork the repository and create a new branch.
2. Make your changes (add features, fix bugs, improve docs).
3. Ensure code style and tests pass.
4. Open a pull request with a clear description.

For major changes, please open an issue first to discuss your proposal.

---

## How to Extend

- **Add Supported Exchanges:** See [how to add supported exchanges](src/backends/exchanges).
- **Add Supported Blockchains:** See [how to add supported blockchains](src/backends/public_ledgers).

---

## Disclaimer ⚠️

This app requires access tokens for your Firefly III instance and API keys for your crypto trading platform account. Only grant the minimum permissions needed (read-only is sufficient for exchanges). Use at your own risk.
