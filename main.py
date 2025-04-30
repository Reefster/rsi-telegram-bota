import ccxt
import pandas as pd
import time
from telegram import Bot
import logging
from statistics import mean

# Config
TELEGRAM_TOKEN = '7995990027:AAFJ3HFQff_l78ngUjmel3Y-WjBPhMcLQPc'
CHAT_ID = '6333148344'
TEST_MODE = True  # Test için düşük eşikler

# Binance Setup
exchange = ccxt.binance({
    'enableRateLimit': True,
    'options': {'defaultType': 'future'}
})

# Logging Setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def get_all_futures_symbols():
    markets = exchange.load_markets()
    futures_symbols = []
    
    for symbol in markets:
        try:
            # Hem USDT hem de futures olduğunu kontrol et
            if '/USDT' in symbol and markets[symbol].get('future', False):
                # Kontrat tipini güvenli şekilde kontrol et
                if 'info' in markets[symbol]:
                    contract_info = markets[symbol]['info']
                    if isinstance(contract_info, dict):
                        if 'contractType' in contract_info:
                            if contract_info['contractType'].lower() in ['perpetual', 'current_quarter', 'next_quarter']:
                                futures_symbols.append(symbol)
                        else:
                            # contractType yoksa ama future True ise yine ekle
                            futures_symbols.append(symbol)
                else:
                    # info kısmı yoksa ama future True ise yine ekle
                    futures_symbols.append(symbol)
        except Exception as e:
            logging.error(f"Symbol {symbol} kontrol hatası: {str(e)}")
            continue
            
    return futures_symbols

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
        
        # TEST MODU için eşik değerler
        if TEST_MODE:
            condition1 = rsi_values['5m'] >= 30  # Normalde 90
            condition2 = rsi_values['15m'] >= 30  # Normalde 90
            condition3 = avg_rsi >= 25  # Normalde 85
        else:
            condition1 = rsi_values['5m'] >= 90
            condition2 = rsi_values['15m'] >= 90
            condition3 = avg_rsi >= 85
        
        logging.info(f"{symbol} | 5m:{rsi_values['5m']:.2f} 15m:{rsi_values['15m']:.2f} Ort:{avg_rsi:.2f}")
        
        return all([condition1, condition2, condition3]), {
            'symbol': symbol.replace(':USDT', ''),
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
        logging.info("Telegram mesajı gönderildi")
    except Exception as e:
        logging.error(f"Telegram hatası: {str(e)}")

def main():
    logging.info(f"Bot başladı... TEST MODU: {'AKTİF' if TEST_MODE else 'PASİF'}")
    while True:
        try:
            symbols = get_all_futures_symbols()
            logging.info(f"Taranacak {len(symbols)} adet pair bulundu")
            
            alert_count = 0
            for symbol in symbols:
                try:
                    meets_condition, data = check_conditions(symbol)
                    if meets_condition:
                        message = (
                            f"🚨 *RSI SİNYALİ* 🚨\n"
                            f"*Pair*: `{data['symbol']}`\n"
                            f"• 5m RSI: `{data['5m']:.2f}`\n"
                            f"• 15m RSI: `{data['15m']:.2f}`\n"
                            f"• 1h RSI: `{data['1h']:.2f}`\n"
                            f"• 4h RSI: `{data['4h']:.2f}`\n"
                            f"• Ortalama: `{data['avg']:.2f}`"
                        )
                        send_telegram_alert(message)
                        alert_count += 1
                        time.sleep(2)
                except Exception as e:
                    logging.error(f"Pair kontrol hatası: {symbol} - {str(e)}")
                
                time.sleep(0.5)  # API rate limit için
                
            logging.info(f"Tarama tamamlandı. {alert_count} sinyal bulundu. 5 dakika bekleniyor...")
            time.sleep(300)
            
        except Exception as e:
            logging.error(f"Ana döngü hatası: {str(e)}")
            time.sleep(60)

if __name__ == '__main__':
    main()
