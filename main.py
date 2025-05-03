import ccxt
import pandas as pd
from telegram import Bot, error as telegram_error
import logging
from statistics import mean
import asyncio
import time
from datetime import datetime
import random
from typing import List, Optional

# Telegram Ayarları
TELEGRAM_TOKEN = '7761091287:AAGEW8OcnfMFUt5_DmAIzBm2I63YgHAcia4'
CHAT_ID = '2123083924'

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

# Stabil Coin Blacklist (USDT çiftleri)
STABLECOIN_BLACKLIST = [
    'USDC/USDT', 'BUSD/USDT', 'DAI/USDT', 'TUSD/USDT', 'PAX/USDT',
    'UST/USDT', 'EUR/USDT', 'GBP/USDT', 'JPY/USDT', 'AUD/USDT',
    'BTC/USDT', 'ETH/USDT'
]

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
        await asyncio.sleep(2)
        return True
    except telegram_error.TimedOut:
        if retry_count < MAX_RETRIES:
            await asyncio.sleep(5)
            return await send_telegram_alert(message, retry_count + 1)
        logging.error("Telegram mesajı gönderilemedi (max retry)")
        return False
    except telegram_error.RetryAfter as e:
        await asyncio.sleep(e.retry_after + 2)
        return await send_telegram_alert(message, retry_count)
    except Exception as e:
        logging.error(f"Telegram hatası: {str(e)}")
        return False

async def fetch_ohlcv(symbol: str, timeframe: str, retry_count: int = 0) -> Optional[List[float]]:
    """OHLCV verisi çekme"""
    try:
        data = exchange.fetch_ohlcv(symbol, timeframe, limit=OHLCV_LIMIT)
        await asyncio.sleep(API_DELAY)
        return data if data else None
    except ccxt.NetworkError:
        if retry_count < 2:
            await asyncio.sleep(5 * (retry_count + 1))
            return await fetch_ohlcv(symbol, timeframe, retry_count + 1)
        return None
    except Exception:
        return None

def calculate_rsi(prices: List[float]) -> float:
    """Optimize RSI hesaplama"""
    if len(prices) < RSI_PERIOD:
        return 50.0
    
    deltas = pd.Series(prices).diff()
    gain = deltas.clip(lower=0)
    loss = -deltas.clip(upper=0)
    
    avg_gain = gain.ewm(alpha=1/RSI_PERIOD, adjust=False).mean().iloc[-1]
    avg_loss = loss.ewm(alpha=1/RSI_PERIOD, adjust=False).mean().iloc[-1]
    
    return 100 - (100 / (1 + (avg_gain / avg_loss))) if avg_loss != 0 else 100

async def get_last_price(symbol: str) -> float:
    """Son fiyat bilgisini al"""
    try:
        ticker = exchange.fetch_ticker(symbol)
        return float(ticker['last'])
    except Exception:
        return 0.0

async def check_symbol(symbol: str) -> bool:
    """Sembol kontrolü"""
    try:
        timeframes = ['5m', '15m', '1h', '4h']
        ohlcv_data = []
        
        for tf in timeframes:
            data = await fetch_ohlcv(symbol, tf)
            if not data or len(data) < RSI_PERIOD:
                return False
            ohlcv_data.append(data)

        # RSI hesaplamaları
        rsi_values = {
            tf: calculate_rsi([x[4] for x in data])
            for tf, data in zip(timeframes, ohlcv_data)
        }
        
        # Son fiyat bilgisi
        last_price = await get_last_price(symbol)
        
        if all([
            rsi_values['5m'] >= 85,
            rsi_values['15m'] >= 85,
            mean([rsi_values['5m'], rsi_values['15m'], rsi_values['1h']]) >= 80
        ]):
            clean_symbol = symbol.replace('/USDT:USDT', '').replace('/USDT', '')
            message = (
                f"💰: {clean_symbol}USDT.P\n"
                f"🔔: High🔴🔴 RSI Alert +85\n"
                f"RSI 5minute: {rsi_values['5m']:.2f}\n"
                f"RSI 15minute: {rsi_values['15m']:.2f}\n"
                f"RSI 1hour: {rsi_values['1h']:.2f}\n"
                f"RSI 4hour: {rsi_values['4h']:.2f}\n"
                f"Last Price: {last_price:.5f}\n"
                f"ScalpingPA"
            )
            await send_telegram_alert(message)
            return True
    except Exception as e:
        logging.error(f"Hata oluştu: {str(e)}")
        pass
    return False

async def process_batch(symbols: List[str]) -> int:
    """Toplu işleme"""
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    
    async def limited_check(symbol: str) -> bool:
        async with semaphore:
            return await check_symbol(symbol)
    
    results = await asyncio.gather(*[limited_check(s) for s in symbols])
    return sum(results)

async def main_loop():
    """Ana döngü"""
    logging.info("⚡ Bot başlatıldı")
    
    while True:
        start_time = time.time()
        try:
            markets = exchange.load_markets()
            symbols = [
                s for s in markets
                if '/USDT' in s
                and markets[s].get('contract')
                and markets[s].get('linear')
                and markets[s].get('active')
                and s not in STABLECOIN_BLACKLIST
            ]
            
            random.shuffle(symbols)
            
            logging.info(f"🔍 {len(symbols)} coin taranıyor (Blacklist: {len(STABLECOIN_BLACKLIST)} coin filtrelendi)...")
            
            alerts = 0
            batch_size = 50
            for i in range(0, len(symbols), batch_size):
                alerts += await process_batch(symbols[i:i + batch_size])
                if i + batch_size < len(symbols):
                    await asyncio.sleep(5)
            
            elapsed = time.time() - start_time
            logging.info(f"✅ Tarama tamamlandı | {alerts} sinyal | {elapsed:.1f}s")
            
            await asyncio.sleep(max(120 - elapsed, 60))
            
        except ccxt.BaseError as e:
            logging.error(f"Binance hatası: {str(e)}")
            await asyncio.sleep(60)
        except Exception as e:
            logging.error(f"Kritik hata: {str(e)}")
            await asyncio.sleep(60)

if __name__ == '__main__':
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        logging.info("⛔ Bot durduruldu")
    except Exception as e:
        logging.error(f"Kritik hata: {str(e)}")