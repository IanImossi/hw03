"""
stock_chart.py

Downloads 1 year of daily closing prices for six tickers with yfinance,
prints a short summary per ticker, and writes a self-contained
stock_chart.html (Chart.js from CDN, data embedded, ticker dropdown).

Run with:
    python stock_chart.py
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

TICKERS = ["AAPL", "MSFT", "NVDA", "JPM", "WMT", "AMZN"]
OUTPUT_FILE = "stock_chart.html"


def ensure_yfinance():
    """Install yfinance with pip if it isn't already available."""
    if importlib.util.find_spec("yfinance") is None:
        print("yfinance not found. Installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "yfinance"])
    else:
        print("yfinance is already installed.")


def download_prices():
    """Return {ticker: [(date_str, close), ...]} for 1 year of daily closes."""
    import yfinance as yf

    data = yf.download(
        TICKERS,
        period="1y",
        interval="1d",
        auto_adjust=True,
        progress=False,
        group_by="column",
    )
    closes = data["Close"]

    prices = {}
    for ticker in TICKERS:
        if ticker not in closes.columns:
            raise RuntimeError(f"No data returned for {ticker}.")
        series = closes[ticker].dropna()
        if series.empty:
            raise RuntimeError(f"No closing prices found for {ticker}.")
        prices[ticker] = [
            (idx.strftime("%Y-%m-%d"), round(float(val), 2))
            for idx, val in series.items()
        ]
    return prices


def print_summary(prices):
    print()
    for ticker in TICKERS:
        rows = prices[ticker]
        print(
            f"{ticker:<5} earliest: {rows[0][0]}  latest: {rows[-1][0]}  "
            f"latest close: ${rows[-1][1]:,.2f}"
        )
    print()


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Stock Chart</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
  body { font-family: system-ui, sans-serif; margin: 2rem auto; max-width: 960px; padding: 0 1rem; }
  label { font-weight: 600; margin-right: 0.5rem; }
  select { font-size: 1rem; padding: 0.3rem 0.5rem; }
  .chart-box { position: relative; height: 480px; margin-top: 1.5rem; }
</style>
</head>
<body>
  <label for="ticker">Ticker:</label>
  <select id="ticker"></select>
  <div class="chart-box"><canvas id="chart"></canvas></div>

<script>
const PRICE_DATA = __DATA__;

const select = document.getElementById("ticker");
Object.keys(PRICE_DATA).forEach(function (t) {
  const opt = document.createElement("option");
  opt.value = t;
  opt.textContent = t;
  select.appendChild(opt);
});

const chart = new Chart(document.getElementById("chart"), {
  type: "line",
  data: { labels: [], datasets: [{
    label: "Close (USD)",
    data: [],
    borderColor: "#2563eb",
    backgroundColor: "rgba(37, 99, 235, 0.1)",
    borderWidth: 2,
    pointRadius: 0,
    pointHoverRadius: 4,
    tension: 0.1
  }]},
  options: {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: "index", intersect: false },
    plugins: {
      legend: { display: false },
      title: { display: true, text: "", font: { size: 18 } }
    },
    scales: {
      x: { title: { display: true, text: "Date" }, ticks: { maxTicksLimit: 12 } },
      y: { title: { display: true, text: "Price (USD)" },
           ticks: { callback: function (v) { return "$" + v; } } }
    }
  }
});

function update(ticker) {
  const rows = PRICE_DATA[ticker];
  chart.data.labels = rows.map(function (r) { return r[0]; });
  chart.data.datasets[0].data = rows.map(function (r) { return r[1]; });
  chart.options.plugins.title.text = ticker + " \\u2014 1-Year Daily Closing Price";
  chart.update();
}

select.addEventListener("change", function () { update(select.value); });
update(select.value);
</script>
</body>
</html>
"""


def write_html(prices):
    html = HTML_TEMPLATE.replace("__DATA__", json.dumps(prices))
    out_path = Path.cwd() / OUTPUT_FILE
    out_path.write_text(html, encoding="utf-8")
    return out_path


def main():
    ensure_yfinance()
    prices = download_prices()
    print_summary(prices)
    out_path = write_html(prices)
    print(f"Saved {OUTPUT_FILE} to {out_path}")


if __name__ == "__main__":
    main()
