import requests
import json

# === Telegram Bot Token ===
BOT_TOKEN = '7761091287:AAGEW8OcnfMFUt5_DmAIzBm2I63YgHAcia4'
def get_updates():
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    response = requests.get(url)
    
    try:
        data = response.json()
        print(json.dumps(data, indent=4))  # Daha okunaklı yazdırır
    except Exception as e:
        print("Hata oluştu:", e)

if __name__ == "__main__":
    get_updates()