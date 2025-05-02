import ccxt
import pandas as pd
from telegram import Bot, error as telegram_error
import logging
from statistics import mean
import asyncio
import time
from datetime import datetime
from typing import List, Dict, Optional

# Telegram Settings
TELEGRAM_TOKEN = '7995990027:AAFJ3HFQff_l78ngUjmel3Y-WjBPhMcLQPc'
CHAT_ID = '6333148344'

# Binance API Settings
exchange = ccxt.binance({
    'enableRateLimit': True,
    'options': {'defaultType': 'future'},
    'timeout': 30000
})

# Logging Settings
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

# Parameters
RSI_PERIOD = 12
OHLCV_LIMIT = 50
API_DELAY = 0.5  # Increased delay for better rate limiting
MAX_CONCURRENT = 10  # Reduced concurrent requests
TELEGRAM_TIMEOUT = 30  # Increased Telegram timeout
MAX_RETRIES = 3  # Max retries for Telegram messages

async def send_telegram_alert(message: str, retry_count: int = 0) -> bool:
    """Improved Telegram message sending with retry mechanism"""
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
        logging.info("Telegram message sent successfully")
        await asyncio.sleep(2)  # Rate limit protection
        return True
    except telegram_error.TimedOut:
        if retry_count < MAX_RETRIES:
            logging.warning(f"Telegram timeout, retrying... ({retry_count + 1}/{MAX_RETRIES})")
            await asyncio.sleep(5)
            return await send_telegram_alert(message, retry_count + 1)
        logging.error("Failed to send Telegram message after retries")
        return False
    except telegram_error.RetryAfter as e:
        wait_time = e.retry_after + 2
        logging.warning(f"Rate limit exceeded. Waiting {wait_time} seconds...")
        await asyncio.sleep(wait_time)
        return await send_telegram_alert(message, retry_count)
    except Exception as e:
        logging.error(f"Telegram error: {str(e)}")
        return False

async def fetch_ohlcv(symbol: str, timeframe: str, retry_count: int = 0) -> Optional[List[float]]:
    """Fetch OHLCV data with retry mechanism"""
    try:
        data = exchange.fetch_ohlcv(symbol, timeframe, limit=OHLCV_LIMIT)
        await asyncio.sleep(API_DELAY)
        return [x[4] for x in data] if data else None
    except ccxt.NetworkError as e:
        if retry_count < 2:  # Max 2 retries for network errors
            wait_time = 5 * (retry_count + 1)
            logging.warning(f"Network error for {symbol} {timeframe}, retrying in {wait_time}s...")
            await asyncio.sleep(wait_time)
            return await fetch_ohlcv(symbol, timeframe, retry_count + 1)
        logging.error(f"Failed to fetch data for {symbol} {timeframe}: {str(e)}")
        return None
    except Exception as e:
        logging.error(f"Error fetching {symbol} {timeframe}: {str(e)}")
        return None

def calculate_rsi(prices: List[float], period: int = RSI_PERIOD) -> float:
    """Optimized RSI calculation"""
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
    """Check RSI conditions for a symbol"""
    try:
        timeframes = ['5m', '15m', '1h', '4h']
        closes = []
        
        for tf in timeframes:
            data = await fetch_ohlcv(symbol, tf)
            if data is None:
                return False
            closes.append(data)

        rsi_values = {
            tf: calculate_rsi(prices)
            for tf, prices in zip(timeframes, closes)
        }
        
        # Calculate average RSI excluding 4h timeframe for more sensitivity
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
        logging.error(f"Error processing {symbol}: {str(e)}", exc_info=True)
    return False

async def process_batch(symbols: List[str]) -> int:
    """Process a batch of symbols with limited concurrency"""
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    
    async def limited_check(symbol: str) -> bool:
        async with semaphore:
            return await check_symbol(symbol)
    
    results = await asyncio.gather(*[limited_check(s) for s in symbols])
    return sum(results)

async def main_loop():
    """Main processing loop"""
    logging.info("⚡ Binance Futures RSI-12 Bot Started")
    
    while True:
        scan_start = time.time()
        try:
            markets = exchange.load_markets()
            # Filter only active USDT futures markets
            symbols = [
                s for s in markets
                if '/USDT' in s
                and markets[s].get('contract', False)
                and markets[s].get('linear', False)
                and markets[s].get('active', False)
            ]
            
            # Prioritize high-volume symbols
            symbols = sorted(symbols, key=lambda x: markets[x]['info']['volume24h'], reverse=True)
            
            logging.info(f"🔍 Scanning {len(symbols)} coins. Top 5: {symbols[:5]}")
            
            # Process in batches to avoid rate limits
            batch_size = 50
            alerts = 0
            for i in range(0, len(symbols), batch_size):
                batch = symbols[i:i + batch_size]
                alerts += await process_batch(batch)
                await asyncio.sleep(5)  # Brief pause between batches
            
            scan_time = time.time() - scan_start
            logging.info(f"✅ Scan completed | {alerts} signals | {scan_time:.2f}s")
            
            # Dynamic sleep based on scan time (minimum 60 seconds)
            sleep_time = max(120 - scan_time, 60)
            await asyncio.sleep(sleep_time)
            
        except Exception as e:
            logging.error(f"⚠️ System error: {str(e)}", exc_info=True)
            await asyncio.sleep(60)

if __name__ == '__main__':
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        logging.info("⛔ Bot stopped by user")
    except Exception as e:
        logging.error(f"Fatal error: {str(e)}", exc_info=True)
