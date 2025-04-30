import ccxt
import pandas as pd
from telegram import Bot
import logging
from statistics import mean
import asyncio
import time
from datetime import datetime

# Telegram Ayarları
TELEGRAM_TOKEN = '7995990027:AAFJ3HFQff_l78ngUjmel3Y-WjBPhMcLQPc'
CHAT_ID = '6333148344'

# Binance API Ayarları
exchange = ccxt.binance({
    'enableRateLimit': True,
    'options': {'defaultType': 'future'},
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

# Parametreler
RSI_PERIOD = 14
OHLCV_LIMIT = 100
API_DELAY = 0.3  # Binance rate limit

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
    except Exception as e:
        logging.error(f"Telegram hatası: {str(e)}")

async def fetch_ohlcv(symbol, timeframe):
    """OHLCV verisi çekme"""
    try:
        data = exchange.fetch_ohlcv(symbol, timeframe, limit=OHLCV_LIMIT)
        await asyncio.sleep(API_DELAY)
        return [x[4] for x in data]  # Sadece kapanış fiyatları
    except Exception as e:
        logging.error(f"{symbol} {timeframe} veri çekme hatası: {str(e)}")
        return None

async def check_symbol(symbol):
    """RSI koşullarını kontrol etme"""
    try:
        # Tüm zaman dilimlerinden veriyi paralel çek
        timeframes = ['5m', '15m', '1h', '4h']
        tasks = [fetch_ohlcv(symbol, tf) for tf in timeframes]
        closes = await asyncio.gather(*tasks)
        
        if None in closes:
            return False
            
        # RSI hesapla
        rsi_values = {
            tf: calculate_rsi(prices) 
            for tf, prices in zip(timeframes, closes)
        }
        
        # Tüm zaman dilimlerinin ortalaması
        avg_all = mean(rsi_values.values())
        
        # Koşullar
        if all([
            rsi_values['5m'] >= 90,
            rsi_values['15m'] >= 90,
            avg_all >= 85
        ]):
            message = (
                f"🚀 *RSI ALERT* 🚀\n"
                f"📈 *Pair*: `{symbol.replace('/USDT', '')}`\n"
                f"• 5m RSI: `{rsi_values['5m']:.2f}`\n"
                f"• 15m RSI: `{rsi_values['15m']:.2f}`\n"
                f"• 1h RSI: `{rsi_values['1h']:.2f}`\n"
                f"• 4h RSI: `{rsi_values['4h']:.2f}`\n"
                f"• Tüm Ortalama: `{avg_all:.2f}`\n"
                f"⏱ `{datetime.now().strftime('%H:%M:%S')}`"
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
            symbols = [s for s in markets 
                      if '/USDT' in s 
                      and markets[s].get('future')]
            
            logging.info(f"🔍 {len(symbols)} futures pair taranıyor...")
            
            alerts = 0
            for symbol in symbols:
                if await check_symbol(symbol):
                    alerts += 1
            
            scan_time = time.time() - scan_start
            logging.info(f"✅ Tarama tamamlandı | {alerts} sinyal | {scan_time:.1f}s")
            
            await asyncio.sleep(max(300 - scan_time, 60))  # 5 dakikada bir tarama
            
        except Exception as e:
            logging.error(f"⚠️ Sistem hatası: {str(e)}")
            await asyncio.sleep(60)

if __name__ == '__main__':
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        logging.info("Bot kapatılıyor...")
