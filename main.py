# ... (diğer importlar ve mevcut kodlar aynı)

# Parametreler
RSI_PERIOD = 12
OHLCV_LIMIT = 50
API_DELAY = 0.5
MAX_CONCURRENT = 10
TELEGRAM_TIMEOUT = 30
MAX_RETRIES = 3

# Stabil Coin Blacklist (USDT çiftleri)
STABLECOIN_BLACKLIST = [
    'USDC/USDT', 'BUSD/USDT', 'DAI/USDT', 'TUSD/USDT', 'PAX/USDT', 
    'UST/USDT', 'EUR/USDT', 'GBP/USDT', 'JPY/USDT', 'AUD/USDT',
    'BTC/USDT', 'ETH/USDT'  # Büyük market cap'li coinler de eklenebilir
]

async def main_loop():
    """Ana döngü"""
    logging.info("⚡ Bot başlatıldı")
    
    while True:
        start_time = time.time()
        try:
            markets = exchange.load_markets()
            symbols = [
                s for s in markets
                if '/USDT' in s
                and markets[s].get('contract')
                and markets[s].get('linear')
                and markets[s].get('active')
                and s not in STABLECOIN_BLACKLIST  # Blacklist kontrolü eklendi
            ]
            
            random.shuffle(symbols)  # Rastgele karıştır
            
            logging.info(f"🔍 {len(symbols)} coin taranıyor (Blacklist: {len(STABLECOIN_BLACKLIST)} coin filtrelendi)...")
            
            alerts = 0
            batch_size = 50
            for i in range(0, len(symbols), batch_size):
                alerts += await process_batch(symbols[i:i + batch_size])
                if i + batch_size < len(symbols):
                    await asyncio.sleep(5)
            
            elapsed = time.time() - start_time
            logging.info(f"✅ Tarama tamamlandı | {alerts} sinyal | {elapsed:.1f}s")
            
            await asyncio.sleep(max(120 - elapsed, 60))
            
        except ccxt.BaseError as e:
            logging.error(f"Binance hatası: {str(e)}")
            await asyncio.sleep(60)
        except Exception as e:
            logging.error(f"Beklenmeyen hata: {str(e)}")
            await asyncio.sleep(60)

# ... (diğer fonksiyonlar aynı)