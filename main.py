import ccxt
import pandas as pd
from telegram import Bot
import logging
from statistics import mean
import asyncio
import time  # Ekledik: süre ölçmek için

# Telegram Ayarları
TELEGRAM_TOKEN = '7995990027:AAFJ3HFQff_l78ngUjmel3Y-WjBPhMcLQPc'
CHAT_ID = '6333148344'

# Binance Ayarları
exchange = ccxt.binance({
    'enableRateLimit': True,
    'options': {'defaultType': 'future'}
})

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# USDT hariç stabil coinler
STABLECOINS = ["USDC", "BUSD", "TUSD", "USDP", "DAI", "FDUSD", "EUR", "EURT", "SUSD", "GUSD", "USTC"]

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
        await bot.send_message(
            chat_id=CHAT_ID,
            text=message,
            parse_mode='Markdown'
        )
        logging.info("Telegram mesajı gönderildi.")
    except Exception as e:
        logging.error(f"Telegram hatası: {str(e)}")

def is_stablecoin(symbol_info):
    base = symbol_info.get('base', '').upper()
    return base in STABLECOINS

async def get_filtered_symbols():
    markets = exchange.load_markets()
    filtered = []
    
    for symbol, market in markets.items():
        try:
            if (market.get('quote') == 'USDT' and 
                market.get('contract') and 
                market.get('active', True) and
                not is_stablecoin(market)):
                filtered.append(symbol)
        except Exception as e:
            logging.error(f"Market {symbol} kontrol hatası: {str(e)}")
            
    logging.info(f"Filtrelenmiş {len(filtered)} sembol bulundu")
    return filtered

async def check_symbol(symbol):
    try:
        timeframes = {
            '5m': exchange.fetch_ohlcv(symbol, '5m', limit=100),
            '15m': exchange.fetch_ohlcv(symbol, '15m', limit=100),
            '1h': exchange.fetch_ohlcv(symbol, '1h', limit=100),
            '4h': exchange.fetch_ohlcv(symbol, '4h', limit=100),
        }

        rsi_values = {
            '5m': calculate_rsi([x[4] for x in timeframes['5m']]),
            '15m': calculate_rsi([x[4] for x in timeframes['15m']]),
            '1h': calculate_rsi([x[4] for x in timeframes['1h']]),
            '4h': calculate_rsi([x[4] for x in timeframes['4h']])
        }
        
        avg_rsi = mean([rsi_values['1h'], rsi_values['4h']])
        
        conditions_met = all([
            rsi_values['5m'] >= 90,
            rsi_values['15m'] >= 90,
            avg_rsi >= 85
        ])
        
        if conditions_met:
            symbol_clean = symbol.replace(':USDT', '').replace('/USDT', '')
            message = (
                f"🚨 *RSI SİNYALİ* 🚨\n"
                f"*Pair*: `{symbol_clean}`\n"
                f"• 5m RSI: `{rsi_values['5m']:.2f}` (≥90)\n"
                f"• 15m RSI: `{rsi_values['15m']:.2f}` (≥90)\n"
                f"• 1h RSI: `{rsi_values['1h']:.2f}`\n"
                f"• 4h RSI: `{rsi_values['4h']:.2f}`\n"
                f"• Ortalama (1h+4h): `{avg_rsi:.2f}` (≥85)"
            )
            await send_telegram_alert(message)
            return True
            
        return False

    except Exception as e:
        logging.error(f"{symbol} hatası: {str(e)}")
        return False

async def main_loop():
    logging.info("Bot başlatıldı. RSI taraması sürekli çalışıyor...")

    while True:
        try:
            start_time = time.time()

            symbols = await get_filtered_symbols()
            alert_count = 0

            for symbol in symbols:
                if await check_symbol(symbol):
                    alert_count += 1
                    await asyncio.sleep(2)  # Telegram rate limit
                await asyncio.sleep(1)  # Binance rate limit

            duration = time.time() - start_time
            logging.info(f"Tarama tamamlandı. {alert_count} sinyal bulundu. Süre: {duration:.1f} saniye.")

        except Exception as e:
            logging.error(f"Ana döngü hatası: {str(e)}")
            await asyncio.sleep(10)

if __name__ == '__main__':
    asyncio.run(main_loop())
