
import ccxt
import pandas as pd
import asyncio
from ta.momentum import RSIIndicator
from telegram import Bot, Update
from telegram.ext import Application, MessageHandler, filters

TELEGRAM_TOKEN = '7995990027:AAFJ3HFQff_l78ngUjmel3Y-WjBPhMcLQPc'
CHAT_ID = '6333148344'

exchange = ccxt.binance()

def get_rsi(df, period=12):
    if df is None or len(df) < period:
        return None
    rsi = RSIIndicator(close=df['close'], window=period)
    return rsi.rsi().iloc[-1]

async def fetch_ohlcv(symbol, timeframe):
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=100)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        return df
    except Exception:
        return None

async def get_price(symbol):
    try:
        ticker = exchange.fetch_ticker(symbol)
        return ticker['last']
    except:
        return None

async def scan(bot):
    try:
        markets = exchange.load_markets()
    except Exception as e:
        print("MARKET LOAD ERROR:", e)
        return

    usdt_pairs = [
        s for s in markets
        if s.endswith('/USDT') and not s.endswith('BULL/USDT') and not s.endswith('BEAR/USDT')
    ]
    results = []

    for symbol in usdt_pairs:
        try:
            df_5m = await fetch_ohlcv(symbol, '5m')
            df_15m = await fetch_ohlcv(symbol, '15m')
            df_1h = await fetch_ohlcv(symbol, '1h')
            df_4h = await fetch_ohlcv(symbol, '4h')

            rsi_5m = get_rsi(df_5m)
            rsi_15m = get_rsi(df_15m)
            rsi_1h = get_rsi(df_1h)
            rsi_4h = get_rsi(df_4h)

            if None in [rsi_5m, rsi_15m, rsi_1h, rsi_4h]:
                continue

            avg_rsi = (rsi_5m + rsi_15m + rsi_1h + rsi_4h) / 4

            if rsi_5m > 90 or rsi_15m > 90 or avg_rsi > 85:
                price = await get_price(symbol)
                results.append({
                    "symbol": symbol.replace("/", ""),
                    "rsi_5m": rsi_5m,
                    "rsi_15m": rsi_15m,
                    "rsi_1h": rsi_1h,
                    "rsi_4h": rsi_4h,
                    "price": price,
                    "avg": avg_rsi
                })
        except:
            continue

    for item in results:
        msg = (
            f"💰: ${item['symbol']}
"
            f"🔔: High🔴🔴 RSI Alert 85+
"
            f"RSI 5minute: {item['rsi_5m']:.2f}
"
            f"RSI 15minute: {item['rsi_15m']:.2f}
"
            f"RSI 1hour: {item['rsi_1h']:.2f}
"
            f"RSI 4hour: {item['rsi_4h']:.2f}
"
            f"Last Price: {item['price']:.7f}"
        )
        await bot.send_message(chat_id=CHAT_ID, text=msg)

async def handle_message(update: Update, context):
    if update.message.text.lower() == "deneme_876543":
        await update.message.reply_text("Bot çalışıyor ve RSI taraması aktif!")

async def start_bot():
    bot = Bot(token=TELEGRAM_TOKEN)
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    async def background_loop():
        while True:
            await scan(bot)
            await asyncio.sleep(300)

    asyncio.create_task(background_loop())
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    await app.updater.idle()

if __name__ == "__main__":
    asyncio.run(start_bot())
