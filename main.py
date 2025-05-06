import ccxt
import pandas as pd
import numpy as np
from telegram import Bot, error as telegram_error
import logging
from statistics import mean
import asyncio
import time
from datetime import datetime
import random
from typing import List, Optional
from ta.momentum import RSIIndicator  # Binance uyumlu RSI (Wilder smoothing)

# === Telegram Ayarları ===
TELEGRAM_BOTS = [
    {'token': '7995990027:AAFJ3HFQff_l78ngUjmel3Y-WjBPhMcLQPc', 'chat_id': '6333148344'},
    {'token': '17761091287:AAGEW8OcnfMFUt5_DmAIzBm2I63YgHAcia4', 'chat_id': '-11002565394717'}
]

# === Binance API ===
exchange = ccxt.binance({
    'enableRateLimit': True,
    'options': {'defaultType': 'future'},
    'timeout': 30000
})

# === Log Ayarları ===
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('rsi_bot.log')
    ]
)

# === Parametreler ===
RSI_PERIOD = 12
OHLCV_LIMIT = RSI_PERIOD + 2  # tamamlanmış 12 + 1 açık mum için yeterli
API_DELAY = 0.2
MAX_CONCURRENT = 10
TELEGRAM_TIMEOUT = 30
MAX_RETRIES = 3

# === Stablecoin Filtreleri ===
STABLECOIN_BLACKLIST = ['USDC/USDT', 'BUSD/USDT', 'DAI/USDT', 'TUSD/USDT', 'PAX/USDT', 'UST/USDT', 'EUR/USDT', 'GBP/USDT', 'JPY/USDT', 'AUD/USDT', 'BTC/USDT', 'ETH/USDT']
STABLECOIN_BASES = ["USDC", "BUSD", "TUSD", "DAI", "FDUSD", "USDP", "EURS", "PAX", "GUSD", "SUSD", "UST", "USDD"]

# === Telegram Gönderimi ===
async def send_telegram_alert(message: str, retry_count: int = 0) -> bool:
    for bot_info in TELEGRAM_BOTS:
        try:
            bot = Bot(token=bot_info['token'])
            await bot.send_message(
                chat_id=bot_info['chat_id'],
                text=message,
                parse_mode='Markdown',
                disable_web_page_preview=True,
                read_timeout=TELEGRAM_TIMEOUT,
                write_timeout=TELEGRAM_TIMEOUT,
                connect_timeout=TELEGRAM_TIMEOUT,
                pool_timeout=TELEGRAM_TIMEOUT
            )
            logging.info(f"Telegram mesaj gönderildi -> {bot_info['chat_id']}")
            await asyncio.sleep(1)
        except telegram_error.TimedOut:
            if retry_count < MAX_RETRIES:
                await asyncio.sleep(5)
                return await send_telegram_alert(message, retry_count + 1)
        except telegram_error.RetryAfter as e:
            await asyncio.sleep(e.retry_after + 2)
            return await send_telegram_alert(message, retry_count)
        except Exception as e:
            logging.error(f"Telegram hatası ({bot_info['chat_id']}): {str(e)}")
    return True

# === Binance OHLCV verisi çekme ===
async def fetch_ohlcv(symbol: str, timeframe: str, retry_count: int = 0) -> Optional[List[float]]:
    try:
        data = exchange.fetch_ohlcv(symbol, timeframe, limit=OHLCV_LIMIT)
        await asyncio.sleep(API_DELAY)
        return data
    except ccxt.NetworkError:
        if retry_count < 2:
            await asyncio.sleep(5 * (retry_count + 1))
            return await fetch_ohlcv(symbol, timeframe, retry_count + 1)
    except Exception:
        pass
    return None

# === Binance uyumlu RSI hesaplama ===
def calculate_rsi_ta(prices: List[float]) -> float:
    close_series = pd.Series(prices)
    rsi = RSIIndicator(close=close_series, window=RSI_PERIOD)
    return rsi.rsi().iloc[-1]

# === RSI değeri (tamamlanmamış mum dahil) ===
async def get_rsi_tradingview(symbol: str, timeframe: str) -> Optional[float]:
    data = await fetch_ohlcv(symbol, timeframe)
    if not data or len(data) < RSI_PERIOD + 1:
        return None

    close_prices = [x[4] for x in data][-12:]  # 12 tamamlanmış kapanış

    try:
        ticker = exchange.fetch_ticker(symbol)
        live_close = float(ticker['last'])  # son açık mumun anlık fiyatı
    except Exception:
        return None

    close_prices.append(live_close)  # kapanmamış mumu dahil et
    return calculate_rsi_ta(close_prices)

# === Son fiyat ===
async def get_last_price(symbol: str) -> float:
    try:
        ticker = exchange.fetch_ticker(symbol)
        return float(ticker['last'])
    except Exception:
        return 0.0

# === RSI sinyal kontrolü ===
async def check_symbol(symbol: str) -> bool:
    try:
        rsi_5m = await get_rsi_tradingview(symbol, "5m")
        if rsi_5m is None or rsi_5m < 180:
            return False

        rsi_15m = await get_rsi_tradingview(symbol, "15m")
        if rsi_15m is None or rsi_15m < 80:
            return False

        rsi_1h = await get_rsi_tradingview(symbol, "1h")
        rsi_4h = await get_rsi_tradingview(symbol, "4h")
        if None in (rsi_1h, rsi_4h):
            return False

        rsi_avg = mean([rsi_5m, rsi_15m, rsi_1h, rsi_4h])
        if rsi_avg < 75:
            return False

        last_price = await get_last_price(symbol)
        clean_symbol = symbol.replace('/USDT:USDT', '').replace('/USDT', '')
        message = (
            f"💰: {clean_symbol}USDT.P\n"
            f"🔔: High🔴🔴 RSI Alert +85\n"
            f"RSI 5minute: {rsi_5m:.2f}\n"
            f"RSI 15minute: {rsi_15m:.2f}\n"
            f"RSI 1hour: {rsi_1h:.2f}\n"
            f"RSI 4hour: {rsi_4h:.2f}\n"
            f"Last Price: {last_price:.5f}\n"
            f"ScalpingPA"
        )
        await send_telegram_alert(message)
        return True
    except Exception as e:
        logging.error(f"{symbol} kontrol hatası: {str(e)}")
        return False

# === Batch kontrol ===
async def process_batch(symbols: List[str]) -> int:
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    async def limited_check(symbol: str) -> bool:
        async with semaphore:
            return await check_symbol(symbol)
    results = await asyncio.gather(*[limited_check(s) for s in symbols])
    return sum(results)

# === Ana döngü ===
async def main_loop():
    logging.info("⚡ Bot başlatıldı")
    while True:
        start_time = time.time()
        try:
            markets = exchange.load_markets()
            symbols = [
                s for s in markets
                if '/USDT' in s and markets[s].get('contract')
                and markets[s].get('linear') and markets[s].get('active')
                and s not in STABLECOIN_BLACKLIST and markets[s]['base'] not in STABLECOIN_BASES
            ]
            random.shuffle(symbols)
            logging.info(f"🔍 {len(symbols)} coin taranıyor...")
            alerts = 0
            batch_size = 50
            for i in range(0, len(symbols), batch_size):
                alerts += await process_batch(symbols[i:i + batch_size])
                if i + batch_size < len(symbols):
                    await asyncio.sleep(3)
            elapsed = time.time() - start_time
            logging.info(f"✅ Tarama tamamlandı | {alerts} sinyal | Süre: {elapsed:.1f}s")
            await asyncio.sleep(max(60 - elapsed, 20))
        except Exception as e:
            logging.error(f"Genel hata: {str(e)}")
            await asyncio.sleep(60)

# === Başlat ===
if __name__ == '__main__':
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        logging.info("⛔ Bot durduruldu")
    except Exception as e:
        logging.error(f"Başlatma hatası: {str(e)}")