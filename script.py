import yfinance as yf

apple = yf.Ticker("AAPL")

# Quarterly income statement: rows are line items, columns are quarter-end dates (newest first)
income = apple.quarterly_income_stmt

latest_quarter = income.columns[0]
revenue = income.loc["Total Revenue", latest_quarter]
net_income = income.loc["Net Income", latest_quarter]

print(f"Apple (AAPL) - quarter ended {latest_quarter.date()}")
print(f"Revenue:    ${revenue / 1e9:,.2f}B")
print(f"Net Income: ${net_income / 1e9:,.2f}B")