import requests
import pandas as pd
import time
import math
from ta.momentum import RSIIndicator

# === Telegram Bilgileri ===
BOT1_TOKEN = "7995990027:AAFJ3HFQff_l78ngUjmel3Y-WjBPhMcLQPc"
BOT1_CHAT_ID = "6333148344"

BOT2_TOKEN = "7761091287:AAGEW8OcnfMFUt5_DmAIzBm2I63YgHAcia4"
BOT2_CHAT_ID = "-1002565394717"

def send_telegram_message(message, token, chat_id):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = {"chat_id": chat_id, "text": message}
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
        rsi = RSIIndicator(close=df['close'], window=12).rsi()
        rsi_value = rsi.iloc[-1]
        if math.isnan(rsi_value):
            return None
        rsi_values[interval] = rsi_value

    avg_rsi = sum(rsi_values.values()) / len(rsi_values)
    return rsi_values, round(avg_rsi, 2)

# === Ana Tarama Döngüsü ===
while True:
    start_time = time.time()
    print("\n🔍 Yeni RSI taraması başlatıldı...\n", flush=True)

    usdt_pairs = get_usdt_pairs()

    for symbol in usdt_pairs:
        try:
            result = calculate_rsi(symbol)
            if result:
                rsi_vals, avg_rsi = result

                print(f"{symbol}: RSI 5m={rsi_vals['5m']:.2f}, RSI 15m={rsi_vals['15m']:.2f}, RSI Ort={avg_rsi:.2f}", flush=True)

                if rsi_vals['5m'] >= 50 and rsi_vals['15m'] >= 50 and avg_rsi >= 45:
                    price = get_klines(symbol, '5m').iloc[-1]['close']

                    message = (
                        f"💰: {symbol}\n"
                        f"🔔: High🔴🔴 RSI Alert +85\n"
                        f"RSI 5minute: {rsi_vals['5m']:.2f}\n"
                        f"RSI 15minute: {rsi_vals['15m']:.2f}\n"
                        f"RSI 1hour: {rsi_vals['1h']:.2f}\n"
                        f"RSI 4hour: {rsi_vals['4h']:.2f}\n"
                        f"Last Price: {price:.5f}\n"
                        f"ScalpingPA"
                    )

                    # Her iki bota mesaj gönder
                    res1 = send_telegram_message(message, BOT1_TOKEN, BOT1_CHAT_ID)
                    res2 = send_telegram_message(message, BOT2_TOKEN, BOT2_CHAT_ID)

                    if res1.status_code == 200 and res2.status_code == 200:
                        print(f"✅ İki bota sinyal gönderildi: {symbol}", flush=True)
                    else:
                        print(f"❌ Gönderim hatası: {symbol}", flush=True)

        except Exception as e:
            print(f"Hata oluştu ({symbol}): {e}", flush=True)

    end_time = time.time()
    duration = round(end_time - start_time, 2)
    print(f"\n✅ RSI taraması tamamlandı. Süre: {duration} saniye.\n", flush=True)

    time.sleep(60)