import requests
import pandas as pd
import time
import math
from ta.momentum import RSIIndicator

# === Configuration ===
BOT1_TOKEN = "7995990027:AAFJ3HFQff_l78ngUjmel3Y-WjBPhMcLQPc"
BOT1_CHAT_ID = "6333148344"
BOT2_TOKEN = "7761091287:AAGEW8OcnfMFUt5_DmAIzBm2I63YgHAcia4"
BOT2_CHAT_ID = "-1002565394717"

# Binance API limits (requests per minute)
API_LIMITS = {
    'klines': 1200,  # Actual limit is 1200 per minute
    'exchangeInfo': 20  # Actual limit is 20 per minute
}

# Request counters and timing
request_counters = {'klines': 0, 'exchangeInfo': 0}
last_reset_time = time.time()

# === Enhanced API Functions with Rate Limiting ===
def check_rate_limit(endpoint):
    global last_reset_time, request_counters
    
    # Reset counters every minute
    if time.time() - last_reset_time > 60:
        request_counters = {'klines': 0, 'exchangeInfo': 0}
        last_reset_time = time.time()
    
    request_counters[endpoint] += 1
    if request_counters[endpoint] >= API_LIMITS[endpoint]:
        sleep_time = 60 - (time.time() - last_reset_time) + 1
        print(f"⚠️ Rate limit approaching for {endpoint}. Sleeping for {sleep_time:.1f} seconds...")
        time.sleep(sleep_time)
        request_counters[endpoint] = 0
        last_reset_time = time.time()

def send_telegram_message(message, token, chat_id):
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = {"chat_id": chat_id, "text": message}
        response = requests.post(url, data=data, timeout=10)
        response.raise_for_status()
        return response
    except Exception as e:
        print(f"Telegram send error: {str(e)}")
        return None

def get_usdt_pairs():
    check_rate_limit('exchangeInfo')
    try:
        url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        usdt_pairs = []
        blacklist = ["USDC", "BUSD", "TUSD", "USDP", "DAI", "FDUSD", "USTC", "EURS", "PAX", "BTCDOM"]

        for symbol in data["symbols"]:
            if (symbol["quoteAsset"] == "USDT" and 
                symbol["contractType"] == "PERPETUAL" and 
                symbol["status"] == "TRADING"):
                base = symbol["baseAsset"]
                if base not in blacklist:
                    usdt_pairs.append(symbol["symbol"])
        return usdt_pairs
    except Exception as e:
        print(f"Error getting USDT pairs: {str(e)}")
        return []

def get_klines(symbol, interval, limit=100):
    check_rate_limit('klines')
    try:
        url = f"https://fapi.binance.com/fapi/v1/klines"
        params = {"symbol": symbol, "interval": interval, "limit": limit}
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        df = pd.DataFrame(data, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_asset_volume', 'number_of_trades',
            'taker_buy_base_volume', 'taker_buy_quote_volume', 'ignore'
        ])
        df['close'] = pd.to_numeric(df['close'])
        return df
    except Exception as e:
        print(f"Error getting klines for {symbol} {interval}: {str(e)}")
        return pd.DataFrame()

def calculate_rsi_single_interval(symbol, interval, window=12):
    try:
        df = get_klines(symbol, interval)
        if df.empty:
            return None
        rsi = RSIIndicator(close=df['close'], window=window).rsi()
        rsi_value = rsi.iloc[-1]
        if math.isnan(rsi_value):
            return None
        return rsi_value
    except Exception as e:
        print(f"RSI calculation error for {symbol} {interval}: {str(e)}")
        return None

# === Main Loop ===
def main_loop():
    while True:
        start_time = time.time()
        print("\n🔍 Yeni RSI taraması başlatıldı...\n", flush=True)
        
        try:
            usdt_pairs = get_usdt_pairs()
            if not usdt_pairs:
                print("⚠️ No USDT pairs found or error fetching pairs")
                time.sleep(60)
                continue
            
            alerted_pairs = set()
            
            for symbol in usdt_pairs:
                try:
                    # First quick check for 5m and 15m
                    rsi_5m = calculate_rsi_single_interval(symbol, '5m')
                    if rsi_5m is None or rsi_5m < 85:
                        continue
                    
                    rsi_15m = calculate_rsi_single_interval(symbol, '15m')
                    if rsi_15m is None or rsi_15m < 85:
                        continue
                    
                    # If we get here, both 5m and 15m are ≥85
                    rsi_1h = calculate_rsi_single_interval(symbol, '1h')
                    rsi_4h = calculate_rsi_single_interval(symbol, '4h')
                    
                    if None in (rsi_1h, rsi_4h):
                        continue
                    
                    avg_rsi = (rsi_5m + rsi_15m + rsi_1h + rsi_4h) / 4
                    if avg_rsi < 80:
                        continue
                    
                    # Final verification before sending
                    current_rsi_5m = calculate_rsi_single_interval(symbol, '5m')
                    current_rsi_15m = calculate_rsi_single_interval(symbol, '15m')
                    current_rsi_1h = calculate_rsi_single_interval(symbol, '1h')
                    current_rsi_4h = calculate_rsi_single_interval(symbol, '4h')
                    
                    if None in (current_rsi_5m, current_rsi_15m, current_rsi_1h, current_rsi_4h):
                        continue
                    
                    if current_rsi_5m < 85 or current_rsi_15m < 85:
                        continue
                    
                    current_avg = (current_rsi_5m + current_rsi_15m + current_rsi_1h + current_rsi_4h) / 4
                    if current_avg < 80:
                        continue
                    
                    price = get_klines(symbol, '5m').iloc[-1]['close']
                    
                    message = (
                        f"💰: {symbol}.P\n"
                        f"🔔: High🔴🔴 RSI Alert +85\n"
                        f"RSI 5minute: {current_rsi_5m:.2f}\n"
                        f"RSI 15minute: {current_rsi_15m:.2f}\n"
                        f"RSI 1hour: {current_rsi_1h:.2f}\n"
                        f"RSI 4hour: {current_rsi_4h:.2f}\n"
                        f"Last Price: {price:.5f}\n"
                        f"ScalpingPA"
                    )
                    
                    res1 = send_telegram_message(message, BOT1_TOKEN, BOT1_CHAT_ID)
                    res2 = send_telegram_message(message, BOT2_TOKEN, BOT2_CHAT_ID)
                    
                    if res1 and res2:
                        print(f"✅ İki bota sinyal gönderildi: {symbol}", flush=True)
                        alerted_pairs.add(symbol)
                    else:
                        print(f"❌ Gönderim hatası: {symbol}", flush=True)
                
                except Exception as e:
                    print(f"Hata oluştu ({symbol}): {str(e)}", flush=True)
            
            end_time = time.time()
            duration = round(end_time - start_time, 2)
            print(f"\n✅ RSI taraması tamamlandı. Süre: {duration} saniye. Alerted pairs: {alerted_pairs}\n", flush=True)
            
            # Adaptive sleep based on rate limits
            elapsed = time.time() - last_reset_time
            if elapsed < 60 and request_counters['klines'] > API_LIMITS['klines'] * 0.8:
                sleep_time = 60 - elapsed + 1
                print(f"⚠️ Approaching rate limit. Sleeping for {sleep_time:.1f} seconds...")
                time.sleep(sleep_time)
            else:
                time.sleep(60)
        
        except Exception as e:
            print(f"Critical error in main loop: {str(e)}")
            time.sleep(60)

if __name__ == "__main__":
    main_loop()