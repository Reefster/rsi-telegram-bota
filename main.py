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

# Binance API Ayarları (DÜZELTİLMİŞ)
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

# Global Bot Instance
bot = Bot(token=TELEGRAM_TOKEN)

# Parametreler
RSI_PERIOD = 12
OHLCV_LIMIT = 50  # Daha hızlı tarama için
API_DELAY = 0.5
MAX_CONCURRENT = 5  # Binance rate limit için güvenli değer

def calculate_rsi(prices, period=RSI_PERIOD):
    """RSI 12 hesaplama (Güvenli versiyon)"""
    if len(prices) < period:
        return 50  # Yeterli veri yoksa nötr değer
    
    deltas = pd.Series(prices).diff()
    gain = deltas.clip(lower=0)
    loss = -deltas.clip(upper=0)
    
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
    
    rs = avg_gain / avg_loss.replace(0, 1e-10)
    return 100 - (100 / (1 + rs)).iloc[-1]

async def send_telegram_alert(message):
    """Güvenli mesaj gönderme"""
    try:
        await bot.send_message(
            chat_id=CHAT_ID,
            text=message,
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
        await asyncio.sleep(2)  # Telegram rate limit koruması
        logging.info("Mesaj gönderildi")
    except Exception as e:
        logging.error(f"Telegram hatası: {str(e)}", exc_info=True)

async def fetch_ohlcv(symbol, timeframe):
    """DÜZELTİLMİŞ veri çekme fonksiyonu"""
    try:
        # DÜZELTME: doğrudan async olmayan çağrı
        data = exchange.fetch_ohlcv(symbol, timeframe, limit=OHLCV_LIMIT)
        await asyncio.sleep(API_DELAY)  # Rate limit koruması
        return [x[4] for x in data] if data else None
    except Exception as e:
        logging.error(f"{symbol} {timeframe} veri hatası: {str(e)}")
        return None

async def check_symbol(symbol):
    """DÜZELTİLMİŞ RSI kontrol"""
    try:
        timeframes = ['5m', '15m', '1h', '4h']
        closes = []
        
        # Sıralı veri çekme (async problemlerini önlemek için)
        for tf in timeframes:
            data = await fetch_ohlcv(symbol, tf)
            if data is None:
                return False
            closes.append(data)
        
        rsi_values = {
            tf: calculate_rsi(prices) 
            for tf, prices in zip(timeframes, closes)
        }
        avg_all = mean(rsi_values.values())
        
        # ORİJİNAL STRATEJİ (RSI 12 ile)
        if all([
            rsi_values['5m'] >= 50,
            rsi_values['15m'] >= 50,
            avg_all >= 45
        ]):
            message = (
                f"🚀 *RSI-12 ALERT* 🚀\n"
                f"📈 *Pair*: `{symbol.replace('/USDT', '')}`\n"
                f"• 5m RSI: `{rsi_values['5m']:.2f}`\n"
                f"• 15m RSI: `{rsi_values['15m']:.2f}`\n"
                f"• 1h RSI: `{rsi_values['1h']:.2f}`\n"
                f"• 4h RSI: `{rsi_values['4h']:.2f}`\n"
                f"⏱ `{datetime.now().strftime('%H:%M:%S')}`"
            )
            await send_telegram_alert(message)
            return True
            
    except Exception as e:
        logging.error(f"{symbol} işlem hatası: {str(e)}", exc_info=True)
    return False

async def main_loop():
    """DÜZELTİLMİŞ ana döngü"""
    logging.info("⚡ Binance Futures RSI-12 Botu Başlatıldı")
    
    while True:
        scan_start = time.time()
        try:
            # DÜZELTME: await olmadan markets yükleme
            markets = exchange.load_markets()
            symbols = [
                s for s in markets 
                if '/USDT' in s 
                and markets[s].get('future')
                and markets[s].get('active')
            ]
            
            logging.info(f"🔍 {len(symbols)} pair taranıyor...")
            
            # Sıralı işlem (async sorunlarını önlemek için)
            alerts = 0
            for symbol in symbols:
                if await check_symbol(symbol):
                    alerts += 1
            
            scan_time = time.time() - scan_start
            logging.info(f"✅ Tarama tamamlandı | {alerts} sinyal | {scan_time:.2f}s")
            
            # 3 dakikalık döngü
            sleep_time = max(180 - scan_time, 30)
            await asyncio.sleep(sleep_time)
            
        except Exception as e:
            logging.error(f"⚠️ Sistem hatası: {str(e)}", exc_info=True)
            await asyncio.sleep(60)

if __name__ == '__main__':
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        logging.info("Bot kapatılıyor...")
    except Exception as e:
        logging.error(f"KRİTİK HATA: {str(e)}", exc_info=True)
