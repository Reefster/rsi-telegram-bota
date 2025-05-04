import requests
import pandas as pd
import time
import math
from ta.momentum import RSIIndicator

# === Telegram Bilgileri ===
BOT_TOKEN = "7761091287:AAGEW8OcnfMFUt5_DmAIzBm2I63YgHAcia4"
CHAT_ID = "2123083924"

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": message}
    response = requests.post(url, data=data)
    return response

def get_usdt_pairs():
    url = "https://api.binance.com/api/v3/exchangeInfo"
    response = requests.get(url)
    data = response.json()
    usdt_pairs = []
    blacklist = ["USDC", "BUSD", "TUSD", "USDP", "DAI", "FDUSD", "USTC", "EURS", "PAX", "USDT"]
    for symbol in data["symbols"]:
        if symbol["quoteAsset"] == "USDT" and symbol["status"] == "TRADING":
            base = symbol["baseAsset"]
            if base not in blacklist:
                usdt_pairs.append(symbol["symbol"])
    return usdt_pairs

def get_klines(symbol, interval, limit=100):
    url = f"https://api.binance.com/api/v3/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    response = requests.get(url, params=params)
    data = response.json()
    df = pd.DataFrame(data, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_asset_volume', 'number_of_trades',
        'taker_buy_base_volume', 'taker_buy_quote_volume', 'ignore'
    ])
    df['close'] = pd.to_numeric(df['close'])
    return df

def calculate_rsi(symbol):
    intervals = ['5m', '15m', '1h', '4h']
    rsi_values = {}

    for interval in intervals:
        df = get_klines(symbol, interval)
        if df.empty:
            return None
        rsi = RSIIndicator(close=df['close'], window=14).rsi()
        rsi_value = rsi.iloc[-1]
        if math.isnan(rsi_value):
            return None
        rsi_values[interval] = rsi_value

    avg_rsi = sum(rsi_values.values()) / len(rsi_values)
    return rsi_values, round(avg_rsi, 2)

# === Ana Tarama Döngüsü ===
while True:
    print("\n🔍 Yeni tarama başlatılıyor...\n")
    usdt_pairs = get_usdt_pairs()

    for symbol in usdt_pairs:
        try:
            result = calculate_rsi(symbol)
            if result:
                rsi_vals, avg_rsi = result
                price = get_klines(symbol, '5m').iloc[-1]['close']

                message = (
                    f"📊 RSI Bilgilendirme: {symbol}\n\n"
                    f"RSI 5m: {rsi_vals['5m']:.2f}\n"
                    f"RSI 15m: {rsi_vals['15m']:.2f}\n"
                    f"RSI 1h: {rsi_vals['1h']:.2f}\n"
                    f"RSI 4h: {rsi_vals['4h']:.2f}\n"
                    f"Ortalama RSI: {avg_rsi:.2f}\n"
                    f"Fiyat: {price:.5f}"
                )

                try:
                    response = send_telegram_message(message)
                    if response.status_code == 200:
                        print(f"✅ Gönderildi: {symbol}")
                except Exception as e:
                    print(f"Telegram gönderim hatası: {e}")

        except Exception as e:
            print(f"Hata {symbol}: {e}") bu kod 2 bota mesaj atabilir mi