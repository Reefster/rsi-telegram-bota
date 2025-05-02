import ccxt
import pandas as pd
from telegram import Bot, error as telegram_error
import logging
from statistics import mean
import asyncio
import time
from datetime import datetime
from typing import List, Optional

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

# Global Bot Instance
bot = Bot(token=TELEGRAM_TOKEN)

# Parametreler
RSI_PERIOD = 12
OHLCV_LIMIT = 50
API_DELAY = 0.5
MAX_CONCURRENT = 10
TELEGRAM_TIMEOUT = 30
MAX_RETRIES = 3

async def send_telegram_alert(message: str, retry_count: int = 0) -> bool:
    """Geliştirilmiş Telegram mesaj gönderim fonksiyonu"""
    try:
        await bot.send_message(
            chat_id=CHAT_ID,
            text=message,
            parse_mode='Markdown',
            disable_web_page_preview=True,
            read_timeout=TELEGRAM_TIMEOUT,
            write_timeout=TELEGRAM_TIMEOUT,
            connect_timeout=TELEGRAM_TIMEOUT,
            pool_timeout=TELEGRAM_TIMEOUT
        )
        logging.info("Telegram mesajı başarıyla gönderildi")
        await asyncio.sleep(2)  # Rate limit koruması
        return True
    except telegram_error.TimedOut:
        if retry_count < MAX_RETRIES:
            logging.warning(f"Telegram timeout, yeniden deniyor... ({retry_count + 1}/{MAX_RETRIES})")
            await asyncio.sleep(5)
            return await send_telegram_alert(message, retry_count + 1)
        logging.error("Telegram mesajı gönderilemedi (max retry)")
        return False
    except telegram_error.RetryAfter as e:
        wait_time = e.retry_after + 2
        logging.warning(f"Rate limit aşıldı. {wait_time} saniye bekleniyor...")
        await asyncio.sleep(wait_time)
        return await send_telegram_alert(message, retry_count)
    except Exception as e:
        logging.error(f"Telegram hatası: {str(e)}")
        return False

async def fetch_ohlcv(symbol: str, timeframe: str, retry_count: int = 0) -> Optional[List[float]]:
    """OHLCV verisi çekme (yeniden deneme mekanizmalı)"""
    try:
        data = exchange.fetch_ohlcv(symbol, timeframe, limit=OHLCV_LIMIT)
        await asyncio.sleep(API_DELAY)
        return [x[4] for x in data] if data else None
    except ccxt.NetworkError as e:
        if retry_count < 2:
            wait_time = 5 * (retry_count + 1)
            logging.warning(f"{symbol} {timeframe} ağ hatası, {wait_time}s sonra yeniden denenecek...")
            await asyncio.sleep(wait_time)
            return await fetch_ohlcv(symbol, timeframe, retry_count + 1)
        logging.error(f"{symbol} {timeframe} veri çekilemedi: {str(e)}")
        return None
    except Exception as e:
        logging.error(f"{symbol} {timeframe} bilinmeyen hata: {str(e)}")
        return None

def calculate_rsi(prices: List[float], period: int = RSI_PERIOD) -> float:
    """Optimize RSI hesaplama"""
    if len(prices) < period:
        return 50.0
    
    deltas = pd.Series(prices).diff()
    gain = deltas.where(deltas > 0, 0.0)
    loss = -deltas.where(deltas < 0, 0.0)
    
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean().iloc[-1]
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean().iloc[-1]
    
    if avg_loss == 0:
        return 100.0 if avg_gain != 0 else 50.0
    
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))

async def check_symbol(symbol: str) -> bool:
    """Bir sembol için RSI koşullarını kontrol et"""
    try:
        timeframes = ['5m', '15m', '1h', '4h']
        closes = []
        
        for tf in timeframes:
            data = await fetch_ohlcv(symbol, tf)
            if data is None or len(data) < RSI_PERIOD:
                return False
            closes.append(data)

        rsi_values = {
            tf: calculate_rsi(prices)
            for tf, prices in zip(timeframes, closes)
        }
        
        avg_rsi = mean([rsi_values['5m'], rsi_values['15m'], rsi_values['1h']])
        
        if all([
            rsi_values['5m'] >= 85,
            rsi_values['15m'] >= 85,
            avg_rsi >= 80
        ]):
            message = (
                f"🚀 *RSI-12 ALERT* 🚀\n"
                f"📈 *Pair*: `{symbol.replace('/USDT:USDT', '').replace('/USDT', '')}`\n"
                f"• 5m RSI: `{rsi_values['5m']:.2f}`\n"
                f"• 15m RSI: `{rsi_values['15m']:.2f}`\n"
                f"• 1h RSI: `{rsi_values['1h']:.2f}`\n"
                f"• 4h RSI: `{rsi_values['4h']:.2f}`\n"
                f"⏱ `{datetime.now().strftime('%H:%M:%S')}`"
            )
            await send_telegram_alert(message)
            return True

    except Exception as e:
        logging.error(f"{symbol} işlenirken hata: {str(e)}", exc_info=True)
    return False

async def process_batch(symbols: List[str]) -> int:
    """Toplu sembol işleme"""
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    
    async def limited_check(symbol: str) -> bool:
        async with semaphore:
            return await check_symbol(symbol)
    
    results = await asyncio.gather(*[limited_check(s) for s in symbols])
    return sum(results)

async def main_loop():
    """Ana işlem döngüsü"""
    logging.info("⚡ Binance Futures RSI-12 Bot Başlatıldı")
    
    while True:
        scan_start = time.time()
        try:
            markets = exchange.load_markets()
            symbols = [
                s for s in markets
                if '/USDT' in s
                and markets[s].get('contract', False)
                and markets[s].get('linear', False)
                and markets[s].get('active', False)
            ]
            
            # Sembolleri rastgele karıştır (dengeli dağılım için)
            import random
            random.shuffle(symbols)
            
            logging.info(f"🔍 {len(symbols)} coin taranıyor. Örnekler: {symbols[:5]}...")
            
            alerts = 0
            batch_size = 50
            for i in range(0, len(symbols), batch_size):
                batch = symbols[i:i + batch_size]
                alerts += await process_batch(batch)
                if i + batch_size < len(symbols):
                    await asyncio.sleep(5)  # Batch'ler arası bekleme
            
            scan_time = time.time() - scan_start
            logging.info(f"✅ Tarama tamamlandı | {alerts} sinyal | {scan_time:.2f}s")
            
            sleep_time = max(120 - scan_time, 60)
            await asyncio.sleep(sleep_time)
            
        except ccxt.BaseError as e:
            logging.error(f"Binance API hatası: {str(e)}")
            await asyncio.sleep(60)
        except Exception as e:
            logging.error(f"Beklenmeyen hata: {str(e)}", exc_info=True)
            await asyncio.sleep(60)

if __name__ == '__main__':
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        logging.info("⛔ Bot kullanıcı tarafından durduruldu")
    except Exception as e:
        logging.error(f"Kritik hata: {str(e)}", exc_info=True)
