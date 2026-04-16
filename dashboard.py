import streamlit as st
import pandas as pd
import pandas_ta as ta
import plotly.graph_objects as go
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timedelta, timezone
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import DataFeed
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, GetOrdersRequest
from alpaca.trading.enums import OrderSide, TimeInForce, QueryOrderStatus
from streamlit_autorefresh import st_autorefresh

# ==========================================
# 1. SETUP & KEYS (From Streamlit Secrets Vault)
# ==========================================
ALPACA_API_KEY = st.secrets["PK76I5OBEQ7J4MWZBH4O35QIXQ"]
ALPACA_SECRET_KEY = st.secrets["BCzKQgatG6eGznUaUEzBcLsCY3LzNJaq1skikmwsHubz"]
SENDER_EMAIL = st.secrets["trading.app.cg@gmail.com"]  # The Gmail sending the alert
SENDER_PASSWORD = st.secrets["fdbi bmuv tahz Ipqt"] # The App Password from Google
CELL_PHONE_EMAIL = st.secrets["5595485468@tmomail.net"] # Your phone number @ your carrier's gateway

# Initialize BOTH Alpaca Clients (same keys, two purposes)
alpaca_data = StockHistoricalDataClient(ALPACA_API_KEY, ALPACA_SECRET_KEY)
alpaca_trader = TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=True)

# ==========================================
# 2. CONFIGURATION
# ==========================================
SYMBOL = "NRDS"
TRADE_QTY = 100  # Shares per trade (~$1,080 at current price)

# ==========================================
# 3. FREE NOTIFICATION FUNCTION
# ==========================================
def fire_alerts(title, message_body):
    try:
        msg = MIMEText(message_body)
        msg['Subject'] = title
        msg['From'] = SENDER_EMAIL
        msg['To'] = CELL_PHONE_EMAIL
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg)
    except Exception as e:
        st.error(f"Alert Failed: {e}")

# ==========================================
# 4. PAPER TRADING FUNCTIONS
# ==========================================
def get_position():
    """Check if we currently hold an NRDS position."""
    try:
        position = alpaca_trader.get_open_position(SYMBOL)
        return position
    except Exception:
        return None

def place_buy_order():
    """Submit a market buy order for NRDS."""
    try:
        order_data = MarketOrderRequest(
            symbol=SYMBOL,
            qty=TRADE_QTY,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY
        )
        order = alpaca_trader.submit_order(order_data=order_data)
        return order
    except Exception as e:
        st.error(f"Buy Order Failed: {e}")
        return None

def place_sell_order():
    """Close the entire NRDS position."""
    try:
        alpaca_trader.close_position(SYMBOL)
        return True
    except Exception as e:
        st.error(f"Sell Order Failed: {e}")
        return None

def get_recent_orders():
    """Get recent NRDS orders for the trade log."""
    try:
        request_params = GetOrdersRequest(
            status=QueryOrderStatus.ALL,
            limit=10
        )
        orders = alpaca_trader.get_orders(filter=request_params)
        # Filter to only NRDS orders
        return [o for o in orders if o.symbol == SYMBOL]
    except Exception:
        return []

# ==========================================
# 5. PAGE CONFIG & AUTOREFRESH
# ==========================================
st.set_page_config(page_title="NRDS Trader", layout="wide")
st_autorefresh(interval=30000, key="live_clock")

# ==========================================
# 6. SIDEBAR SAFEGUARDS
# ==========================================
st.sidebar.markdown("### 🛡️ 8-Layer Safeguards")
st.sidebar.markdown("**Next Earnings:** May 6, 2026")
earnings_guard = st.sidebar.checkbox("Earnings Blackout Active (May 1 - May 8)")
circuit_breaker = st.sidebar.checkbox("Circuit Breaker (3 Losses / $50 Down)")
trend_guard = st.sidebar.checkbox("Trend Guard Active")

st.sidebar.markdown("---")
st.sidebar.markdown("### 🤖 Auto-Trading")
auto_trade_enabled = st.sidebar.checkbox("Enable Paper Trading", value=True)
st.sidebar.caption(f"Trade Size: {TRADE_QTY} shares per signal")

if earnings_guard or circuit_breaker:
    st.error("🚨 TRADING HALTED: A critical safeguard is active.")
    st.stop()

# ==========================================
# 7. DATA FETCHING FUNCTION
# ==========================================
@st.cache_data(ttl=15)
def get_nrds_data():
    now = datetime.now(timezone.utc)
    start_date = now - timedelta(days=3)
    request_params = StockBarsRequest(
        symbol_or_symbols=SYMBOL,
        timeframe=TimeFrame.Minute,
        start=start_date,
        feed=DataFeed.IEX
    )
    bars = alpaca_data.get_stock_bars(request_params).df
    if bars.empty:
        return pd.DataFrame()
    bars = bars.reset_index(level=0, drop=True)

    # Calculate Indicators
    bars.ta.bbands(length=20, std=2.0, append=True)
    bars.ta.rsi(length=10, append=True)
    bars.ta.vwap(append=True)

    # Standardize column names dynamically
    col_map = {}
    for col in bars.columns:
        if col.startswith('BBL_'): col_map[col] = 'lower_bb'
        elif col.startswith('BBU_'): col_map[col] = 'upper_bb'
        elif col.startswith('BBM_'): col_map[col] = 'mid_bb'
        elif col.startswith('BBB_'): col_map[col] = 'bb_bandwidth'
        elif col.startswith('BBP_'): col_map[col] = 'bb_percent'
        elif col.startswith('RSI_'): col_map[col] = 'rsi'
        elif col.startswith('VWAP_'): col_map[col] = 'calc_vwap'
    bars = bars.rename(columns=col_map)

    # Fix duplicate vwap columns (Alpaca has one, pandas-ta adds another)
    if 'vwap' in bars.columns and 'calc_vwap' in bars.columns:
        bars = bars.drop(columns=['vwap'])
        bars = bars.rename(columns={'calc_vwap': 'vwap'})
    elif 'calc_vwap' in bars.columns:
        bars = bars.rename(columns={'calc_vwap': 'vwap'})

    return bars

# ==========================================
# 8. MAIN DASHBOARD UI
# ==========================================
st.title("📈 NRDS Mean Reversion Strategy (Paper Trading)")
st.caption(f"Last Data Sync: {datetime.now().strftime('%H:%M:%S')} PDT")

try:
    df = get_nrds_data()

    if df.empty or len(df) < 20:
        st.warning("Not enough data. Market may be closed.")
        st.stop()

    # Get latest values (force to float to avoid Series formatting errors)
    current_price = float(df['close'].iloc[-1])
    lower_band = float(df['lower_bb'].iloc[-1])
    upper_band = float(df['upper_bb'].iloc[-1])
    current_rsi = float(df['rsi'].iloc[-1])
    current_vwap = float(df['vwap'].iloc[-1])

    st.subheader(f"Current NRDS Price: ${current_price:.2f}")

    # --- SIGNAL LOGIC (unchanged from your original rules) ---
    signal = "NEUTRAL"
    signal_detail = "Waiting for a setup."

    if current_price < lower_band and current_rsi < 30 and not trend_guard:
        signal = "BUY"
        signal_detail = f"Price ${current_price:.2f} < Lower BB ${lower_band:.2f} AND RSI {current_rsi:.1f} < 30"
    elif current_price > upper_band and current_rsi > 70 and not trend_guard:
        signal = "SELL"
        signal_detail = f"Price ${current_price:.2f} > Upper BB ${upper_band:.2f} AND RSI {current_rsi:.1f} > 70"

    # --- DISPLAY SIGNAL & INDICATORS ---
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### 🚦 Current Signal")
        if signal == "BUY":
            st.success(f"**{signal}** - {signal_detail}")
        elif signal == "SELL":
            st.error(f"**{signal}** - {signal_detail}")
        else:
            st.info(f"**{signal}** - {signal_detail}")

    with col2:
        st.markdown("### 📊 Live Indicators")
        st.write(f"**RSI (10):** {current_rsi:.1f}")
        st.write(f"**VWAP:** ${current_vwap:.2f}")
        st.write(f"**Lower Band:** ${lower_band:.2f}")
        st.write(f"**Upper Band:** ${upper_band:.2f}")

    # ==========================================
    # 9. AUTO-TRADING ENGINE
    # ==========================================
    st.markdown("---")
    st.markdown("### 🤖 Paper Trading Engine")

    # Check current position
    position = get_position()

    if position:
        pos_qty = int(float(position.qty))
        pos_avg = float(position.avg_entry_price)
        pos_pnl = float(position.unrealized_pl)
        pos_pnl_pct = float(position.unrealized_plpc) * 100
        pnl_color = "green" if pos_pnl >= 0 else "red"
        st.markdown(
            f"**Current Position:** {pos_qty} shares @ ${pos_avg:.2f} | "
            f"P&L: <span style='color:{pnl_color}'>${pos_pnl:.2f} ({pos_pnl_pct:+.2f}%)</span>",
            unsafe_allow_html=True
        )
    else:
        st.markdown("**Current Position:** No open position (FLAT)")

    # Session state prevents duplicate orders on 30-sec refresh
    if 'last_signal_acted' not in st.session_state:
        st.session_state.last_signal_acted = None

    # --- EXECUTE TRADES ---
    if auto_trade_enabled:
        trade_executed = False

        # BUY: Signal is BUY + No existing position + Haven't already acted on this BUY
        if signal == "BUY" and position is None and st.session_state.last_signal_acted != "BUY":
            order = place_buy_order()
            if order:
                st.session_state.last_signal_acted = "BUY"
                trade_executed = True
                fire_alerts(
                    "NRDS AUTO-BUY",
                    f"Bought {TRADE_QTY} shares of NRDS at ~${current_price:.2f}"
                )
                st.success(f"AUTO-BUY: {TRADE_QTY} shares of NRDS at ~${current_price:.2f}")

        # SELL: Signal is SELL + We hold a position + Haven't already acted on this SELL
        elif signal == "SELL" and position is not None and st.session_state.last_signal_acted != "SELL":
            result = place_sell_order()
            if result:
                st.session_state.last_signal_acted = "SELL"
                trade_executed = True
                fire_alerts(
                    "NRDS AUTO-SELL",
                    f"Sold NRDS position at ~${current_price:.2f}"
                )
                st.success(f"AUTO-SELL: Closed NRDS position at ~${current_price:.2f}")

        # NEUTRAL: Reset the tracker so we can act on the next signal
        elif signal == "NEUTRAL":
            st.session_state.last_signal_acted = None

        # Status messages
        if not trade_executed:
            if signal == "BUY" and position is not None:
                st.info("BUY signal active but already holding a position.")
            elif signal == "SELL" and position is None:
                st.info("SELL signal active but no position to sell.")
            elif signal == "NEUTRAL":
                st.info("Auto-trading ON. Waiting for BUY or SELL signal...")
    else:
        st.warning("Auto-trading is OFF. Toggle it on in the sidebar.")

    # ==========================================
    # 10. RECENT TRADE LOG
    # ==========================================
    st.markdown("---")
    st.markdown("### 📋 Recent Trade Log")

    recent_orders = get_recent_orders()
    if recent_orders:
        log_data = []
        for order in recent_orders:
            log_data.append({
                "Time": order.submitted_at.strftime("%m/%d %H:%M") if order.submitted_at else "N/A",
                "Side": order.side.value.upper(),
                "Qty": str(order.qty),
                "Status": order.status.value,
                "Fill Price": f"${float(order.filled_avg_price):.2f}" if order.filled_avg_price else "Pending",
            })
        st.table(pd.DataFrame(log_data))
    else:
        st.info("No trades yet. The bot will execute when signals fire!")

    # ==========================================
    # 11. CHART
    # ==========================================
    st.markdown("### 📈 Live Chart")

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df.index, y=df['close'],
        line=dict(color='white', width=1), name='Price'
    ))
    if 'vwap' in df.columns:
        fig.add_trace(go.Scatter(
            x=df.index, y=df['vwap'],
            line=dict(color='orange', width=2), name='VWAP'
        ))
    fig.add_trace(go.Scatter(
        x=df.index, y=df['upper_bb'],
        line=dict(color='red', width=1, dash='dash'), name='Upper BB'
    ))
    fig.add_trace(go.Scatter(
        x=df.index, y=df['lower_bb'],
        line=dict(color='green', width=1, dash='dash'), name='Lower BB'
    ))
    fig.update_layout(
        xaxis_rangeslider_visible=False,
        height=500,
        template='plotly_dark'
    )
    st.plotly_chart(fig, use_container_width=True)

except Exception as e:
    st.error(f"Error: {e}")