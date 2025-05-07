import requests
import pandas as pd
import time
import math
import asyncio
import aiohttp
from ta.momentum import RSIIndicator
from datetime import datetime

# === Telegram Ayarları ===
BOT1_TOKEN = "7995990027:AAFJ3HFQff_l78ngUjmel3Y-WjBPhMcLQPc"
BOT1_CHAT_ID = "6333148344"
BOT2_TOKEN = "7761091287:AAGEW8OcnfMFUt5_DmAIzBm2I63YgHAcia4"
BOT2_CHAT_ID = "-1002565394717"

# === Binance API Ayarları ===
API_URL = "https://fapi.binance.com"
KLINES_LIMIT = 50
RSI_WINDOW = 12
MAX_CONCURRENT_REQUESTS = 15  # Güvenli eşzamanlı istek sayısı
REQUEST_DELAY = 0.05  # İstekler arası bekleme (saniye)

# === Sembol Filtreleme ===
STABLE_COINS = ["USDC", "BUSD", "TUSD", "USDP", "DAI", "FDUSD", "USTC", "EURS", "PAX"]

class Scanner:
    def __init__(self):
        self.scan_count = 0
        self.last_scan_time = None
        self.request_counter = 0
        self.last_reset_time = time.time()

    async def log(self, message):
        """Detaylı log kaydı"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {message}")

    async def check_rate_limit(self):
        """API rate limit kontrolü"""
        current_time = time.time()
        if current_time - self.last_reset_time > 60:  # Her dakika sıfırla
            self.request_counter = 0
            self.last_reset_time = current_time
        
        self.request_counter += 1
        if self.request_counter >= 1000:  # Binance limitine yaklaştığımızda
            wait_time = 60 - (current_time - self.last_reset_time) + 1
            await self.log(f"⚠️ API limitine yaklaşıldı. {wait_time:.1f}s bekleniyor...")
            await asyncio.sleep(wait_time)
            self.request_counter = 0
            self.last_reset_time = time.time()

    async def send_telegram_alert(self, session, symbol, rsi_values, price):
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
        
        try:
            tasks = []
            for bot_token, chat_id in [(BOT1_TOKEN, BOT1_CHAT_ID), (BOT2_TOKEN, BOT2_CHAT_ID)]:
                url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                tasks.append(session.post(url, data={"chat_id": chat_id, "text": message}))
            
            await asyncio.gather(*tasks)
            await self.log(f"✅ Sinyal gönderildi: {symbol}")
            return True
        except Exception as e:
            await self.log(f"❌ Telegram gönderim hatası ({symbol}): {str(e)}")
            return False

    async def get_usdt_futures_pairs(self, session):
        try:
            await self.check_rate_limit()
            async with session.get(f"{API_URL}/fapi/v1/exchangeInfo", timeout=10) as response:
                data = await response.json()
                pairs = [
                    symbol['symbol'] for symbol in data['symbols']
                    if symbol['quoteAsset'] == 'USDT' 
                    and symbol['contractType'] == 'PERPETUAL'
                    and symbol['status'] == 'TRADING'
                    and not any(coin in symbol['baseAsset'] for coin in STABLE_COINS)
                ]
                await self.log(f"📊 Toplam {len(pairs)} USDT futures sembolü bulundu")
                return pairs
        except Exception as e:
            await self.log(f"❌ Sembol listesi alınamadı: {str(e)}")
            return []

    async def get_klines(self, session, symbol, interval):
        try:
            await self.check_rate_limit()
            params = {'symbol': symbol, 'interval': interval, 'limit': KLINES_LIMIT}
            async with session.get(f"{API_URL}/fapi/v1/klines", params=params, timeout=5) as response:
                data = await response.json()
                await self.log(f"🔍 {symbol} {interval} verisi alındı")
                return [float(candle[4]) for candle in data]
        except Exception as e:
            await self.log(f"❌ {symbol} {interval} veri alım hatası: {str(e)}")
            return None

    async def calculate_rsi(self, closes):
        if len(closes) < RSI_WINDOW + 1:
            return None
        df = pd.DataFrame(closes, columns=['close'])
        return RSIIndicator(df['close'], window=RSI_WINDOW).rsi().iloc[-1]

    async def scan_symbol(self, session, symbol):
        try:
            intervals = ['5m', '15m', '1h', '4h']
            tasks = [self.get_klines(session, symbol, interval) for interval in intervals]
            results = await asyncio.gather(*tasks)
            
            if any(result is None for result in results):
                return None
            
            rsi_values = {}
            for interval, closes in zip(intervals, results):
                rsi = await self.calculate_rsi(closes)
                if rsi is None:
                    return None
                rsi_values[interval] = rsi
            
            await self.log(f"📈 {symbol} RSI değerleri: 5m={rsi_values['5m']:.2f} 15m={rsi_values['15m']:.2f} 1h={rsi_values['1h']:.2f} 4h={rsi_values['4h']:.2f}")
            
            if (rsi_values['5m'] >= 85 and 
                rsi_values['15m'] >= 85 and 
                (rsi_values['5m'] + rsi_values['15m'] + rsi_values['1h'] + rsi_values['4h']) / 4 >= 80):
                
                current_price = results[0][-1]
                await self.send_telegram_alert(session, symbol, rsi_values, current_price)
                return symbol
            
            return None
        except Exception as e:
            await self.log(f"❌ {symbol} taranırken hata: {str(e)}")
            return None

    async def run_scan(self, session, symbols):
        self.scan_count += 1
        start_time = time.time()
        await self.log(f"🔄 Tarama #{self.scan_count} başlatılıyor ({len(symbols)} sembol)")
        
        # Sembolleri küçük gruplara ayır
        batch_size = MAX_CONCURRENT_REQUESTS
        alerted_symbols = []
        
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i:i + batch_size]
            tasks = [self.scan_symbol(session, symbol) for symbol in batch]
            results = await asyncio.gather(*tasks)
            alerted_symbols.extend([res for res in results if res is not None])
            
            # API limitlerini koru
            await asyncio.sleep(REQUEST_DELAY)
        
        scan_duration = time.time() - start_time
        await self.log(f"✅ Tarama #{self.scan_count} tamamlandı (Süre: {scan_duration:.2f}s)")
        await self.log(f"🚨 Sinyal gönderilenler: {alerted_symbols or 'Yok'}")
        return alerted_symbols

    async def main(self):
        connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT_REQUESTS)
        async with aiohttp.ClientSession(connector=connector) as session:
            while True:
                symbols = await self.get_usdt_futures_pairs(session)
                if symbols:
                    await self.run_scan(session, symbols)
                
                # Dinamik bekleme süresi
                current_time = time.time()
                if self.last_scan_time:
                    elapsed = current_time - self.last_scan_time
                    sleep_time = max(1, 5 - elapsed)  # Minimum 1s, maksimum 5s bekleme
                else:
                    sleep_time = 1
                
                await self.log(f"⏳ Sonraki tarama için {sleep_time:.1f}s bekleniyor...")
                await asyncio.sleep(sleep_time)
                self.last_scan_time = time.time()

if __name__ == "__main__":
    scanner = Scanner()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(scanner.main())
    except KeyboardInterrupt:
        loop.close()
        print("\n🔴 Tarayıcı durduruldu")