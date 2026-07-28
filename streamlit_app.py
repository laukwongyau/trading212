"""Trading212 portfolio tracker: holdings, return on investment, and recent activity."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from t212_client import Trading212Client, Trading212Error

st.set_page_config(page_title="Trading212 Portfolio Tracker", page_icon="📈", layout="wide")

CURRENCY_SYMBOLS = {"GBP": "£", "EUR": "€", "USD": "$"}

# dataviz palette (references/palette.md) - fixed roles, not decorative choices.
COLOR_BLUE = "#2a78d6"
COLOR_GOOD = "#0ca30c"
COLOR_CRITICAL = "#d03b3b"
COLOR_MUTED = "#898781"


def clean_ticker(ticker: str) -> str:
    """Trading212 tickers look like AAPL_US_EQ; show the leading symbol."""
    return ticker.split("_")[0] if ticker else ticker


def currency_symbol(code: str | None) -> str:
    if not code:
        return ""
    return CURRENCY_SYMBOLS.get(code, f"{code} ")


def fmt_money(value: float, symbol: str) -> str:
    return f"{symbol}{value:,.2f}"


@st.cache_data(ttl=60, show_spinner="Fetching account data...")
def load_account(api_key: str, live: bool) -> tuple[dict, dict]:
    client = Trading212Client(api_key, live)
    return client.account_info(), client.account_cash()


@st.cache_data(ttl=60, show_spinner="Fetching holdings...")
def load_portfolio(api_key: str, live: bool) -> list[dict]:
    client = Trading212Client(api_key, live)
    return client.portfolio()


@st.cache_data(ttl=120, show_spinner="Fetching order history...")
def load_orders(api_key: str, live: bool, max_items: int) -> list[dict]:
    client = Trading212Client(api_key, live)
    return client.orders(max_items=max_items)


@st.cache_data(ttl=120, show_spinner="Fetching dividends...")
def load_dividends(api_key: str, live: bool, max_items: int) -> list[dict]:
    client = Trading212Client(api_key, live)
    return client.dividends(max_items=max_items)


def build_holdings_df(positions: list[dict]) -> pd.DataFrame:
    rows = []
    for pos in positions:
        quantity = pos.get("quantity", 0) or 0
        avg_price = pos.get("averagePrice", 0) or 0
        current_price = pos.get("currentPrice", 0) or 0
        ppl = pos.get("ppl", 0) or 0
        market_value = quantity * current_price
        cost_basis = quantity * avg_price
        pl_pct = (ppl / cost_basis * 100) if cost_basis else 0.0
        rows.append(
            {
                "Ticker": clean_ticker(pos.get("ticker", "")),
                "Full symbol": pos.get("ticker", ""),
                "Quantity": quantity,
                "Avg price": avg_price,
                "Current price": current_price,
                "Market value": market_value,
                "P/L": ppl,
                "P/L %": pl_pct,
            }
        )
    df = pd.DataFrame(rows)
    if not df.empty:
        total_value = df["Market value"].sum()
        df["Weight %"] = (df["Market value"] / total_value * 100) if total_value else 0.0
        df = df.sort_values("Market value", ascending=False).reset_index(drop=True)
    return df


def render_allocation_chart(df: pd.DataFrame, symbol: str) -> None:
    top = df.head(7)
    rest_value = df["Market value"].iloc[7:].sum() if len(df) > 7 else 0.0
    labels = list(top["Ticker"])
    values = list(top["Market value"])
    if rest_value > 0:
        labels.append("Other")
        values.append(rest_value)

    fig = go.Figure(
        go.Bar(
            x=values,
            y=labels,
            orientation="h",
            marker_color=COLOR_BLUE,
            text=[fmt_money(v, symbol) for v in values],
            textposition="outside",
        )
    )
    fig.update_layout(
        title="Allocation by market value",
        xaxis_title=None,
        yaxis=dict(autorange="reversed"),
        margin=dict(l=10, r=10, t=40, b=10),
        height=380,
        showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True)


def render_pl_chart(df: pd.DataFrame, symbol: str) -> None:
    ordered = df.sort_values("P/L")
    gains = ordered[ordered["P/L"] >= 0]
    losses = ordered[ordered["P/L"] < 0]

    fig = go.Figure()
    if len(losses):
        fig.add_trace(
            go.Bar(
                x=losses["P/L"],
                y=losses["Ticker"],
                orientation="h",
                name="Loss",
                marker_color=COLOR_CRITICAL,
                text=[fmt_money(v, symbol) for v in losses["P/L"]],
                textposition="outside",
            )
        )
    if len(gains):
        fig.add_trace(
            go.Bar(
                x=gains["P/L"],
                y=gains["Ticker"],
                orientation="h",
                name="Profit",
                marker_color=COLOR_GOOD,
                text=[fmt_money(v, symbol) for v in gains["P/L"]],
                textposition="outside",
            )
        )
    fig.update_layout(
        title="Unrealized profit / loss by holding",
        margin=dict(l=10, r=10, t=40, b=10),
        height=380,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    st.plotly_chart(fig, use_container_width=True)


def build_orders_df(orders: list[dict]) -> pd.DataFrame:
    rows = []
    for order in orders:
        rows.append(
            {
                "Date": order.get("dateExecuted") or order.get("dateModified") or order.get("dateCreated"),
                "Ticker": clean_ticker(order.get("ticker", "")),
                "Type": order.get("type"),
                "Status": order.get("status"),
                "Quantity": order.get("filledQuantity") or order.get("quantity"),
                "Fill price": order.get("fillPrice"),
                "Value": order.get("filledValue") or order.get("fillResult"),
            }
        )
    df = pd.DataFrame(rows)
    if not df.empty:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        df = df.sort_values("Date", ascending=False).reset_index(drop=True)
    return df


def build_dividends_df(dividends: list[dict]) -> pd.DataFrame:
    rows = []
    for div in dividends:
        rows.append(
            {
                "Date": div.get("paidOn"),
                "Ticker": clean_ticker(div.get("ticker", "")),
                "Quantity": div.get("quantity"),
                "Amount": div.get("amount"),
                "Type": div.get("type"),
            }
        )
    df = pd.DataFrame(rows)
    if not df.empty:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        df = df.sort_values("Date", ascending=False).reset_index(drop=True)
    return df


def render_dividends_chart(df: pd.DataFrame, symbol: str) -> None:
    monthly = df.dropna(subset=["Date"]).copy()
    if monthly.empty:
        return
    monthly["Month"] = monthly["Date"].dt.to_period("M").dt.to_timestamp()
    grouped = monthly.groupby("Month", as_index=False)["Amount"].sum()
    fig = go.Figure(
        go.Bar(
            x=grouped["Month"],
            y=grouped["Amount"],
            marker_color=COLOR_BLUE,
            text=[fmt_money(v, symbol) for v in grouped["Amount"]],
            textposition="outside",
        )
    )
    fig.update_layout(
        title="Dividends received by month",
        margin=dict(l=10, r=10, t=40, b=10),
        height=320,
        showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True)


def get_api_key() -> tuple[str | None, bool]:
    """Returns (api_key, from_secrets)."""
    secret_key = st.secrets.get("trading212", {}).get("api_key") if hasattr(st, "secrets") else None
    if secret_key:
        return secret_key, True
    return st.session_state.get("api_key"), False


def sidebar_controls() -> tuple[str | None, bool]:
    st.sidebar.header("Connection")
    secret_key, from_secrets = get_api_key()

    if from_secrets:
        st.sidebar.success("Using API key from .streamlit/secrets.toml")
        api_key = secret_key
    else:
        api_key = st.sidebar.text_input(
            "Trading212 API key",
            type="password",
            help=(
                "Generate this in the Trading212 app under Settings -> API (Beta). "
                "Kept only in this browser session's memory, never written to disk or logged."
            ),
            key="api_key",
        )

    live = st.sidebar.radio(
        "Account environment",
        options=["Live", "Practice (demo)"],
        help="Use Practice if your API key was generated for a demo/practice account.",
    ) == "Live"

    if st.sidebar.button("Refresh data"):
        st.cache_data.clear()

    st.sidebar.caption(
        "Data is cached for 1-2 minutes per Trading212's API rate limits. "
        "Click Refresh to force a reload."
    )
    return api_key, live


def main() -> None:
    st.title("📈 Trading212 Portfolio Tracker")

    api_key, live = sidebar_controls()
    if not api_key:
        st.info(
            "Enter your Trading212 API key in the sidebar to get started. "
            "You can create one in the Trading212 app: **Settings -> API (Beta) -> Generate API key**, "
            "with read access to Portfolio, Orders and Account History."
        )
        return

    try:
        account_info, account_cash = load_account(api_key, live)
        positions = load_portfolio(api_key, live)
    except Trading212Error as exc:
        st.error(str(exc))
        return

    symbol = currency_symbol(account_info.get("currencyCode"))
    holdings_df = build_holdings_df(positions)

    invested = account_cash.get("invested", holdings_df["Market value"].sub(holdings_df["P/L"]).sum() if not holdings_df.empty else 0.0)
    ppl = account_cash.get("ppl", holdings_df["P/L"].sum() if not holdings_df.empty else 0.0)
    free_cash = account_cash.get("free", 0.0)
    total_value = holdings_df["Market value"].sum() if not holdings_df.empty else 0.0
    account_total = total_value + free_cash
    return_pct = (ppl / invested * 100) if invested else 0.0

    tab_overview, tab_holdings, tab_transactions, tab_dividends = st.tabs(
        ["Overview", "Holdings", "Transactions", "Dividends"]
    )

    with tab_overview:
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total account value", fmt_money(account_total, symbol))
        col2.metric("Invested", fmt_money(invested, symbol))
        col3.metric(
            "Unrealized P/L",
            fmt_money(ppl, symbol),
            delta=f"{return_pct:+.2f}%",
        )
        col4.metric("Free cash", fmt_money(free_cash, symbol))

        if holdings_df.empty:
            st.info("No open positions found on this account.")
        else:
            render_allocation_chart(holdings_df, symbol)

    with tab_holdings:
        if holdings_df.empty:
            st.info("No open positions found on this account.")
        else:
            display_df = holdings_df.drop(columns=["Full symbol"]).copy()
            st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Avg price": st.column_config.NumberColumn(format=f"{symbol}%.2f"),
                    "Current price": st.column_config.NumberColumn(format=f"{symbol}%.2f"),
                    "Market value": st.column_config.NumberColumn(format=f"{symbol}%.2f"),
                    "P/L": st.column_config.NumberColumn(format=f"{symbol}%.2f"),
                    "P/L %": st.column_config.NumberColumn(format="%.2f%%"),
                    "Weight %": st.column_config.NumberColumn(format="%.1f%%"),
                },
            )
            render_pl_chart(holdings_df, symbol)

    with tab_transactions:
        max_items = st.slider("Number of recent orders to show", 10, 200, 50, step=10)
        try:
            orders = load_orders(api_key, live, max_items)
        except Trading212Error as exc:
            st.error(str(exc))
            orders = []
        orders_df = build_orders_df(orders)
        if orders_df.empty:
            st.info("No orders found.")
        else:
            ticker_filter = st.text_input("Filter by ticker")
            filtered = orders_df
            if ticker_filter:
                filtered = filtered[filtered["Ticker"].str.contains(ticker_filter, case=False, na=False)]
            st.dataframe(
                filtered,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Fill price": st.column_config.NumberColumn(format=f"{symbol}%.2f"),
                    "Value": st.column_config.NumberColumn(format=f"{symbol}%.2f"),
                },
            )

    with tab_dividends:
        max_div_items = st.slider("Number of dividend records to show", 10, 200, 50, step=10, key="div_slider")
        try:
            dividends = load_dividends(api_key, live, max_div_items)
        except Trading212Error as exc:
            st.error(str(exc))
            dividends = []
        dividends_df = build_dividends_df(dividends)
        if dividends_df.empty:
            st.info("No dividend payments found.")
        else:
            total_dividends = dividends_df["Amount"].sum()
            st.metric("Total dividends received (shown period)", fmt_money(total_dividends, symbol))
            render_dividends_chart(dividends_df, symbol)
            st.dataframe(
                dividends_df,
                use_container_width=True,
                hide_index=True,
                column_config={"Amount": st.column_config.NumberColumn(format=f"{symbol}%.2f")},
            )


if __name__ == "__main__":
    main()
