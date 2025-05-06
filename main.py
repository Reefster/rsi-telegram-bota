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
    url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
    response = requests.get(url)
    data = response.json()
    usdt_pairs = []
    blacklist = ["USDC", "BUSD", "TUSD", "USDP", "DAI", "FDUSD", "USTC", "EURS", "PAX", "BTCDOM"]

    for symbol in data["symbols"]:
        if symbol["quoteAsset"] == "USDT" and symbol["contractType"] == "PERPETUAL" and symbol["status"] == "TRADING":
            base = symbol["baseAsset"]
            if base not in blacklist:
                usdt_pairs.append(symbol["symbol"])
    return usdt_pairs

def get_klines(symbol, interval, limit=100):
    url = f"https://fapi.binance.com/fapi/v1/klines"
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

def calculate_rsi_single_interval(symbol, interval, window=12):
    df = get_klines(symbol, interval)
    if df.empty:
        return None
    rsi = RSIIndicator(close=df['close'], window=window).rsi()
    rsi_value = rsi.iloc[-1]
    if math.isnan(rsi_value):
        return None
    return rsi_value

# === Ana Tarama Döngüsü ===
while True:
    start_time = time.time()
    print("\n🔍 Yeni RSI taraması başlatıldı...\n", flush=True)

    usdt_pairs = get_usdt_pairs()

    for symbol in usdt_pairs:
        try:
            rsi_5m = calculate_rsi_single_interval(symbol, '5m')
            if rsi_5m is None or rsi_5m < 89:
                continue

            rsi_15m = calculate_rsi_single_interval(symbol, '15m')
            if rsi_15m is None or rsi_15m < 89:
                continue

            rsi_1h = calculate_rsi_single_interval(symbol, '1h')
            rsi_4h = calculate_rsi_single_interval(symbol, '4h')
            if None in (rsi_1h, rsi_4h):
                continue

            avg_rsi = round((rsi_5m + rsi_15m + rsi_1h + rsi_4h) / 4, 2)
            if avg_rsi < 85:
                continue

            # === Gönderimden önce verileri güncelle ===
            rsi_5m = calculate_rsi_single_interval(symbol, '5m')
            rsi_15m = calculate_rsi_single_interval(symbol, '15m')
            rsi_1h = calculate_rsi_single_interval(symbol, '1h')
            rsi_4h = calculate_rsi_single_interval(symbol, '4h')
            price = get_klines(symbol, '5m').iloc[-1]['close']

            if None in (rsi_5m, rsi_15m, rsi_1h, rsi_4h):
                continue

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