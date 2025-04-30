import ccxt
import pandas as pd
import time
from telegram import Bot
import logging
from statistics import mean

# Config
TELEGRAM_TOKEN = '7995990027:AAFJ3HFQff_l78ngUjmel3Y-WjBPhMcLQPc'
CHAT_ID = '6333148344'

# Binance Setup
exchange = ccxt.binance({
    'enableRateLimit': True,
    'options': {'defaultType': 'future'}  # Futures market için
})

# Logging Setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def get_usdt_futures_symbols():
    markets = exchange.load_markets()
    return [symbol for symbol in markets 
            if '/USDT' in symbol 
            and markets[symbol].get('future', False)]  # 'future' kontrolü eklendi

def calculate_rsi(prices, period=14):
    deltas = pd.Series(prices).diff(1)
    gain = deltas.where(deltas > 0, 0)
    loss = -deltas.where(deltas < 0, 0)
    
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    
    rs = avg_gain / avg_loss.replace(0, 1e-10)
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1]

def check_conditions(symbol):
    try:
        timeframes = {
            '5m': exchange.fetch_ohlcv(symbol, '5m', limit=100),
            '15m': exchange.fetch_ohlcv(symbol, '15m', limit=100),
            '1h': exchange.fetch_ohlcv(symbol, '1h', limit=100),
            '4h': exchange.fetch_ohlcv(symbol, '4h', limit=100)
        }
        
        rsi_values = {tf: calculate_rsi([x[4] for x in data]) 
                     for tf, data in timeframes.items()}
        
        avg_rsi = mean(rsi_values.values())
        
        # Koşullar
        condition1 = rsi_values['5m'] >= 90
        condition2 = rsi_values['15m'] >= 90
        condition3 = avg_rsi >= 85
        
        return all([condition1, condition2, condition3]), {
            'symbol': symbol,
            '5m': rsi_values['5m'],
            '15m': rsi_values['15m'],
            '1h': rsi_values['1h'],
            '4h': rsi_values['4h'],
            'avg': avg_rsi
        }
        
    except Exception as e:
        logging.error(f"Hata: {symbol} - {str(e)}")
        return False, None

def send_telegram_alert(message):
    try:
        bot = Bot(token=TELEGRAM_TOKEN)
        bot.send_message(
            chat_id=CHAT_ID,
            text=message,
            parse_mode='Markdown'
        )
    except Exception as e:
        logging.error(f"Telegram hatası: {str(e)}")

def main():
    logging.info("Bot başladı...")
    while True:
        try:
            symbols = get_usdt_futures_symbols()
            logging.info(f"Taranacak {len(symbols)} adet pair bulundu")
            
            for symbol in symbols:
                meets_condition, data = check_conditions(symbol)
                if meets_condition:
                    message = (
                        f"🚨 *RSI SİNYALİ* 🚨\n"
                        f"*Pair*: {data['symbol']}\n"
                        f"• 5m RSI: {data['5m']:.2f}\n"
                        f"• 15m RSI: {data['15m']:.2f}\n"
                        f"• Ortalama RSI: {data['avg']:.2f}"
                    )
                    send_telegram_alert(message)
                    time.sleep(5)
                
                logging.info(f"Kontrol: {symbol} - 5m:{data['5m']:.2f} 15m:{data['15m']:.2f} Ort:{data['avg']:.2f}")
                time.sleep(1)
                
        except Exception as e:
            logging.error(f"Ana döngü hatası: {str(e)}")
            time.sleep(60)
        
        time.sleep(300)  # 5 dakika bekle

if __name__ == '__main__':
    main()
