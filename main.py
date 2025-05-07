import requests
import pandas as pd
import time
import math
import asyncio
import aiohttp
from ta.momentum import RSIIndicator

# === Telegram Ayarları ===
BOT1_TOKEN = "7995990027:AAFJ3HFQff_l78ngUjmel3Y-WjBPhMcLQPc"
BOT1_CHAT_ID = "6333148344"
BOT2_TOKEN = "7761091287:AAGEW8OcnfMFUt5_DmAIzBm2I63YgHAcia4"
BOT2_CHAT_ID = "-1002565394717"

# === Binance API Ayarları ===
API_URL = "https://fapi.binance.com"
KLINES_LIMIT = 50  # Daha az veri daha hızlı yanıt
RSI_WINDOW = 12
MAX_CONCURRENT_REQUESTS = 20  # Daha agresif tarama için

# === Sembol Filtreleme ===
STABLE_COINS = ["USDC", "BUSD", "TUSD", "USDP", "DAI", "FDUSD", "USTC", "EURS", "PAX"]

async def send_telegram_alert(session, symbol, rsi_values, price):
    message = (
        f"💰: {symbol}.P\n"
        f"🔔: High🔴🔴 RSI Alert +85\n"
        f"RSI 5minute: {rsi_values['5m']:.2f}\n"
        f"RSI 15minute: {rsi_values['15m']:.2f}\n"
        f"RSI 1hour: {rsi_values['1h']:.2f}\n"
        f"RSI 4hour: {rsi_values['4h']:.2f}\n"
        f"Last Price: {price:.5f}\n"
        f"ScalpingPA"
    )
    
    tasks = []
    for bot_token, chat_id in [(BOT1_TOKEN, BOT1_CHAT_ID), (BOT2_TOKEN, BOT2_CHAT_ID)]:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        tasks.append(session.post(url, data={"chat_id": chat_id, "text": message}))
    
    responses = await asyncio.gather(*tasks, return_exceptions=True)
    return all(not isinstance(res, Exception) for res in responses)

async def get_usdt_futures_pairs(session):
    try:
        async with session.get(f"{API_URL}/fapi/v1/exchangeInfo", timeout=10) as response:
            data = await response.json()
            return [
                symbol['symbol'] for symbol in data['symbols']
                if symbol['quoteAsset'] == 'USDT' 
                and symbol['contractType'] == 'PERPETUAL'
                and symbol['status'] == 'TRADING'
                and not any(coin in symbol['baseAsset'] for coin in STABLE_COINS)
            ]
    except Exception as e:
        print(f"❌ Sembol listesi alınamadı: {str(e)}")
        return []

async def get_klines(session, symbol, interval):
    try:
        params = {'symbol': symbol, 'interval': interval, 'limit': KLINES_LIMIT}
        async with session.get(f"{API_URL}/fapi/v1/klines", params=params, timeout=3) as response:  # Daha kısa timeout
            data = await response.json()
            return [float(candle[4]) for candle in data]  # Close prices
    except Exception as e:
        print(f"❌ {symbol} {interval} veri alım hatası: {str(e)}")
        return None

async def check_symbol(session, symbol):
    try:
        intervals = ['5m', '15m', '1h', '4h']
        tasks = [get_klines(session, symbol, interval) for interval in intervals]
        results = await asyncio.gather(*tasks)
        
        if any(result is None for result in results):
            return None
        
        rsi_values = {}
        for interval, closes in zip(intervals, results):
            if len(closes) >= RSI_WINDOW + 1:
                df = pd.DataFrame(closes, columns=['close'])
                rsi = RSIIndicator(df['close'], window=RSI_WINDOW).rsi()
                rsi_values[interval] = rsi.iloc[-1]
            else:
                return None
        
        if (rsi_values['5m'] >= 85 and 
            rsi_values['15m'] >= 85 and 
            (rsi_values['5m'] + rsi_values['15m'] + rsi_values['1h'] + rsi_values['4h']) / 4 >= 80):
            
            current_price = results[0][-1]
            await send_telegram_alert(session, symbol, rsi_values, current_price)
            return symbol
    
    except Exception as e:
        print(f"❌ {symbol} işlenirken hata: {str(e)}")
    
    return None

async def main_scan():
    connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT_REQUESTS)
    async with aiohttp.ClientSession(connector=connector) as session:
        while True:
            start_time = time.time()
            print("\n🔍 Yeni tarama başlatılıyor...")
            
            symbols = await get_usdt_futures_pairs(session)
            if not symbols:
                print("⚠️ Sembol listesi alınamadı. 10 saniye bekleniyor...")
                await asyncio.sleep(10)
                continue
            
            print(f"📊 {len(symbols)} sembol taranıyor...")
            
            # Tüm sembolleri tek seferde tarama (daha agresif)
            batch_size = len(symbols)  # Tüm sembolleri aynı anda tara
            alerted_symbols = []
            
            for i in range(0, len(symbols), batch_size):
                batch = symbols[i:i + batch_size]
                tasks = [check_symbol(session, symbol) for symbol in batch]
                results = await asyncio.gather(*tasks)
                alerted_symbols.extend([res for res in results if res is not None])
            
            scan_duration = time.time() - start_time
            print(f"\n✅ Tarama tamamlandı (Süre: {scan_duration:.2f}s)")
            print(f"📢 Sinyal gönderilen semboller: {alerted_symbols or 'Yok'}")
            
            # 1 saniyelik mini bekleme (sürekli döngü için)
            await asyncio.sleep(1)

if __name__ == "__main__":
    # Daha yüksek performans için event loop ayarı
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(main_scan())
    except KeyboardInterrupt:
        pass
    finally:
        loop.close()