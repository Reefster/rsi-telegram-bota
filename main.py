import requests
import pandas as pd
import time
import math
from ta.momentum import RSIIndicator

# === Telegram Ayarları ===
BOT1_TOKEN = "7995990027:AAFJ3HFQff_l78ngUjmel3Y-WjBPhMcLQPc"
BOT1_CHAT_ID = "6333148344"
BOT2_TOKEN = "7761091287:AAGEW8OcnfMFUt5_DmAIzBm2I63YgHAcia4"
BOT2_CHAT_ID = "-1002565394717"

# === Binance API Ayarları ===
API_URL = "https://fapi.binance.com"
KLINES_LIMIT = 100
RSI_WINDOW = 12

# === Sembol Filtreleme ===
STABLE_COINS = ["USDC", "BUSD", "TUSD", "USDP", "DAI", "FDUSD", "USTC", "EURS", "PAX"]

def send_telegram_alerts(symbol, rsi_5m, rsi_15m, rsi_1h, rsi_4h, price):
    message = (
        f"💰: {symbol}.P\n"
        f"🔔: High🔴🔴 RSI Alert +85\n"
        f"RSI 5minute: {rsi_5m:.2f}\n"
        f"RSI 15minute: {rsi_15m:.2f}\n"
        f"RSI 1hour: {rsi_1h:.2f}\n"
        f"RSI 4hour: {rsi_4h:.2f}\n"
        f"Last Price: {price:.5f}\n"
        f"ScalpingPA"
    )
    
    # İki bota aynı anda mesaj gönder
    success = True
    for bot_token, chat_id in [(BOT1_TOKEN, BOT1_CHAT_ID), (BOT2_TOKEN, BOT2_CHAT_ID)]:
        try:
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            data = {"chat_id": chat_id, "text": message}
            response = requests.post(url, data=data, timeout=5)
            if response.status_code != 200:
                print(f"❌ {chat_id} gönderim hatası: {symbol}")
                success = False
        except Exception as e:
            print(f"❌ {chat_id} bağlantı hatası: {str(e)}")
            success = False
    
    return success

def get_usdt_futures_pairs():
    try:
        response = requests.get(f"{API_URL}/fapi/v1/exchangeInfo", timeout=10)
        data = response.json()
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

def get_latest_data(symbol):
    """Son verileri tek seferde alır"""
    intervals = ['5m', '15m', '1h', '4h']
    data = {}
    
    for interval in intervals:
        try:
            params = {'symbol': symbol, 'interval': interval, 'limit': KLINES_LIMIT}
            response = requests.get(f"{API_URL}/fapi/v1/klines", params=params, timeout=5)
            candles = response.json()
            close_prices = [float(candle[4]) for candle in candles]
            data[interval] = close_prices
        except Exception as e:
            print(f"❌ {symbol} {interval} veri alım hatası: {str(e)}")
            return None
    
    return data

def calculate_all_rsi(data):
    """Tüm RSI değerlerini hesaplar"""
    rsi_values = {}
    for interval in data:
        if len(data[interval]) >= RSI_WINDOW + 1:
            df = pd.DataFrame(data[interval], columns=['close'])
            rsi = RSIIndicator(df['close'], window=RSI_WINDOW).rsi()
            rsi_values[interval] = rsi.iloc[-1]
        else:
            return None
    return rsi_values

def check_initial_conditions(rsi_values):
    """İlk koşulları kontrol eder"""
    if (rsi_values.get('5m', 0) >= 85 and 
        rsi_values.get('15m', 0) >= 85):
        avg = (rsi_values['5m'] + rsi_values['15m'] + 
               rsi_values['1h'] + rsi_values['4h']) / 4
        return avg >= 80
    return False

def main():
    print("🚀 Binance USDT Futures RSI Tarayıcısı Başlatıldı\n")
    print(f"🤖 BOT1: {BOT1_CHAT_ID} | BOT2: {BOT2_CHAT_ID}\n")
    
    while True:
        start_time = time.time()
        symbols = get_usdt_futures_pairs()
        
        if not symbols:
            print("⚠️ Sembol listesi alınamadı. 60 saniye bekleniyor...")
            time.sleep(60)
            continue
        
        print(f"🔍 Toplam {len(symbols)} sembol taraniyor...")
        alerted_symbols = []
        
        for symbol in symbols:
            try:
                # 1. Adım: Tüm verileri tek seferde al
                data = get_latest_data(symbol)
                if not data:
                    continue
                
                # 2. Adım: RSI değerlerini hesapla
                rsi_values = calculate_all_rsi(data)
                if not rsi_values:
                    continue
                
                # 3. Adım: İlk koşulları kontrol et
                if check_initial_conditions(rsi_values):
                    # 4. Adım: Mesaj göndermeden önce SON DURUMU tekrar kontrol et
                    final_data = get_latest_data(symbol)
                    if not final_data:
                        continue
                        
                    final_rsi = calculate_all_rsi(final_data)
                    if not final_rsi:
                        continue
                        
                    # Son fiyatı al
                    current_price = final_data['5m'][-1]
                    
                    # Mesajı gönder
                    if send_telegram_alerts(
                        symbol,
                        final_rsi['5m'],
                        final_rsi['15m'],
                        final_rsi['1h'],
                        final_rsi['4h'],
                        current_price
                    ):
                        alerted_symbols.append(symbol)
                        print(f"✅ Sinyal gönderildi: {symbol}")
                
            except Exception as e:
                print(f"❌ Kritik hata ({symbol}): {str(e)}")
            
            # API limitlerini aşmamak için küçük bir bekleme
            time.sleep(0.2)
        
        scan_duration = time.time() - start_time
        print(f"\n✅ Tarama tamamlandı (Süre: {scan_duration:.2f}s)")
        print(f"📢 Sinyal gönderilen semboller: {alerted_symbols or 'Yok'}")
        print(f"⏳ Sonraki tarama için 60 saniye bekleniyor...\n")
        time.sleep(60)

if __name__ == "__main__":
    main()