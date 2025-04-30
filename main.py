import ccxt
import pandas as pd
import time
from telegram import Bot
import logging
from statistics import mean
import asyncio

# Telegram Ayarları
TELEGRAM_TOKEN = '7995990027:AAFJ3HFQff_l78ngUjmel3Y-WjBPhMcLQPc'
CHAT_ID = '6333148344'

# Binance Ayarları
exchange = ccxt.binance({
    'enableRateLimit': True,
    'options': {'defaultType': 'future'}
})

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_all_futures_symbols():
    markets = exchange.load_markets()
    return [
        symbol for symbol in markets
        if symbol.endswith('/USDT') and markets[symbol].get('future', False)
    ]

def calculate_rsi(prices, period=14):
    deltas = pd.Series(prices).diff()
    gain = deltas.where(deltas > 0, 0)
    loss = -deltas.where(deltas < 0, 0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss.replace(0, 1e-10)
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1]

async def send_telegram_alert(message):
    try:
        bot = Bot(token=TELEGRAM_TOKEN)
        await bot.send_message(chat_id=CHAT_ID, text=message, parse_mode='Markdown')
        logging.info("Telegram mesajı gönderildi.")
    except Exception as e:
        logging.error(f"Telegram hatası: {str(e)}")

async def check_symbol(symbol):
    try:
        timeframes = {
            '5m': exchange.fetch_ohlcv(symbol, '5m', limit=100),
            '15m': exchange.fetch_ohlcv(symbol, '15m', limit=100),
            '1h': exchange.fetch_ohlcv(symbol, '1h', limit=100),
            '4h': exchange.fetch_ohlcv(symbol, '4h', limit=100),
        }

        rsi_values = {tf: calculate_rsi([x[4] for x in data]) for tf, data in timeframes.items()}
        avg_rsi = mean(rsi_values.values())

        if rsi_values['5m'] >= 90 or rsi_values['15m'] >= 90 or avg_rsi >= 85:
            symbol_clean = symbol.replace(':USDT', '').replace('/USDT', '')
            message = (
                f"🚨 *RSI SİNYALİ* 🚨\n"
                f"*Pair*: `{symbol_clean}`\n"
                f"• 5m RSI: `{rsi_values['5m']:.2f}`\n"
                f"• 15m RSI: `{rsi_values['15m']:.2f}`\n"
                f"• 1h RSI: `{rsi_values['1h']:.2f}`\n"
                f"• 4h RSI: `{rsi_values['4h']:.2f}`\n"
                f"• Ortalama RSI: `{avg_rsi:.2f}`\n"
            )
            await send_telegram_alert(message)
            return 1
        return 0

    except Exception as e:
        logging.error(f"{symbol} hatası: {str(e)}")
        return 0

async def main_loop():
    logging.info("Bot başlatıldı. RSI taraması başlıyor...")
    while True:
        try:
            symbols = get_all_futures_symbols()
            logging.info(f"{len(symbols)} adet coin taranacak...")

            tasks = [check_symbol(symbol) for symbol in symbols]
            results = await asyncio.gather(*tasks)
            found = sum(results)

            logging.info(f"{found} sinyal bulundu. 1 dakika bekleniyor...\n")
            await asyncio.sleep(60)  # 1 dakika bekleme
        except Exception as e:
            logging.error(f"Ana döngü hatası: {str(e)}")
            await asyncio.sleep(60)

if __name__ == '__main__':
    asyncio.run(main_loop())
