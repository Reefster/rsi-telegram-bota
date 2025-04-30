import ccxt
import pandas as pd
from telegram import Bot
import logging
from statistics import mean
import asyncio
import time

# Telegram Ayarları
TELEGRAM_TOKEN = '7995990027:AAFJ3HFQff_l78ngUjmel3Y-WjBPhMcLQPc'
CHAT_ID = '6333148344'

# Binance API Ayarları
exchange = ccxt.binance({
    'enableRateLimit': True,
    'options': {
        'defaultType': 'future',
        'adjustForTimeDifference': True
    },
    'timeout': 30000
})

# Logging Ayarları
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('rsi_bot.log')
    ]
)

# Stabil Coin Filtresi
STABLECOINS = ["USDC", "BUSD", "TUSD", "USDP", "DAI", "FDUSD", "EUR", "EURT", "SUSD", "GUSD", "USTC"]

# Performans Optimizasyonu
RSI_PERIOD = 14
OHLCV_LIMIT = 100
TELEGRAM_DELAY = 1.2  # Telegram rate limit: 30 messages/sec
BINANCE_DELAY = 0.3   # Binance rate limit: 1200 requests/min

def calculate_rsi(prices, period=RSI_PERIOD):
    """Optimize RSI hesaplama fonksiyonu"""
    deltas = pd.Series(prices).diff()
    gain = deltas.clip(lower=0)
    loss = -deltas.clip(upper=0)
    
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
    
    rs = avg_gain / avg_loss.replace(0, 1e-10)
    return 100 - (100 / (1 + rs)).iloc[-1]

async def send_telegram_alert(message):
    """Güvenli mesaj gönderme fonksiyonu"""
    try:
        bot = Bot(token=TELEGRAM_TOKEN)
        await bot.send_message(
            chat_id=CHAT_ID,
            text=message,
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
        logging.info("Telegram mesajı gönderildi")
        await asyncio.sleep(TELEGRAM_DELAY)
    except Exception as e:
        logging.error(f"Telegram hatası: {str(e)}")

def filter_futures_symbols(markets):
    """Yüksek performanslı sembol filtreleme"""
    return [
        symbol for symbol, market in markets.items()
        if (market.get('quote') == 'USDT'
            and market.get('contract')
            and market.get('active')
            and market.get('base') not in STABLECOINS)
    ]

async def fetch_ohlcv_batch(symbol, timeframes):
    """Toplu OHLCV verisi çekme"""
    results = {}
    for tf in timeframes:
        try:
            data = exchange.fetch_ohlcv(symbol, tf, limit=OHLCV_LIMIT)
            results[tf] = [x[4] for x in data]  # Sadece kapanış fiyatları
            await asyncio.sleep(BINANCE_DELAY)
        except Exception as e:
            logging.error(f"{symbol} {tf} veri çekme hatası: {str(e)}")
            results[tf] = None
    return results

async def check_symbol(symbol):
    """RSI koşullarını kontrol etme"""
    try:
        timeframes = ['5m', '15m', '1h', '4h']
        closes = await fetch_ohlcv_batch(symbol, timeframes)
        
        if None in closes.values():
            return False
            
        rsi_values = {
            tf: calculate_rsi(prices) 
            for tf, prices in closes.items()
        }
        
        avg_rsi = mean([rsi_values['1h'], rsi_values['4h']])
        
        # Tüm koşulların kontrolü
        if all([
            rsi_values['5m'] >= 90,
            rsi_values['15m'] >= 90,
            avg_rsi >= 85
        ]):
            message = (
                f"🚀 *RSI ALERT* 🚀\n"
                f"📈 *Pair*: `{symbol.replace('/USDT', '')}`\n"
                f"• 5m RSI: `{rsi_values['5m']:.2f}`\n"
                f"• 15m RSI: `{rsi_values['15m']:.2f}`\n"
                f"• 1h/4h Avg: `{avg_rsi:.2f}`\n"
                f"⏱ `{pd.Timestamp.now().strftime('%H:%M:%S')}`"
            )
            await send_telegram_alert(message)
            return True
            
    except Exception as e:
        logging.error(f"{symbol} işlem hatası: {str(e)}")
    
    return False

async def main_loop():
    """Ana işlem döngüsü"""
    logging.info("⚡ Binance Futures RSI Botu Başlatıldı")
    
    while True:
        scan_start = time.time()
        try:
            markets = exchange.load_markets()
            symbols = filter_futures_symbols(markets)
            logging.info(f"🔍 {len(symbols)} futures pair taranıyor...")
            
            alerts = 0
            for symbol in symbols:
                if await check_symbol(symbol):
                    alerts += 1
            
            scan_time = time.time() - scan_start
            logging.info(f"✅ Tarama tamamlandı | {alerts} sinyal | {scan_time:.1f}s")
            
            await asyncio.sleep(max(60 - scan_time, 10))  # Dakikada bir tarama
            
        except Exception as e:
            logging.error(f"⚠️ Sistem hatası: {str(e)}")
            await asyncio.sleep(30)

if __name__ == '__main__':
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        logging.info("Bot kapatılıyor...")
