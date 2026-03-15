# build 6.1.6
from flask import Flask, Response, request
import requests
import os
import json
import sys
from datetime import datetime, timedelta
import openai
from supabase import create_client, Client

app = Flask(__name__)

# 🔐 Config
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
NASE_API_HESLO = os.environ.get("NASE_API_HESLO", "v0idbot@dam") # Tvoje heslo
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "")
TG_KANAL_ZAKLAD = os.environ.get("TG_KANAL_ZAKLAD", "") 

supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def log_now(msg):
    print(msg, flush=True)

def posli_tg_spravu(kanal, text):
    if not TG_BOT_TOKEN or not kanal:
        log_now("⚠️ TG Error: Missing Token or Channel ID")
        return
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": kanal, "text": text, "parse_mode": "HTML"}
    try:
        r = requests.post(url, json=payload, timeout=10)
        log_now(f"📡 TG Response: {r.status_code} - {r.text}")
    except Exception as e:
        log_now(f"❌ TG Fatal Error: {e}")

def get_market_data(mint):
    if not mint: return {"symbol": "ERR", "price": 0, "mc": 0}
    try:
        r = requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{mint}", timeout=5)
        res = r.json()
        if res.get("pairs"):
            p = res["pairs"][0]
            return {
                "symbol": p.get("baseToken", {}).get("symbol", "UNK"),
                "price": float(p.get("priceUsd", 0)),
                "mc": float(p.get("fdv", 0) or p.get("marketCap", 1))
            }
    except: pass
    return {"symbol": str(mint)[:4].upper(), "price": 0, "mc": 0}

@app.route('/webhook', methods=['POST'])
def handle_webhook():
    api_key = request.args.get("api_key")
    if api_key != NASE_API_HESLO:
        return "Unauthorized", 401
    
    data = request.json
    log_now(f"📡 WEBHOOK START: Received {len(data) if data else 0} transactions")

    for tx in data:
        # Helius Enhanced Webhook posiela swapy ako ZOZNAM vnútri events
        swaps = tx.get("events", {}).get("swap")
        if not swaps:
            continue
        
        # Ak je to jeden objekt, dáme ho do zoznamu, ak je to zoznam, ideme cez neho
        if not isinstance(swaps, list):
            swaps = [swaps]

        for s in swaps:
            t_in = s.get("tokenInMint")
            t_out = s.get("tokenOutMint")
            mint = t_in if t_in != "So11111111111111111111111111111111111111112" else t_out
            
            if not mint: continue

            m_data = get_market_data(mint)
            amount = abs(float(s.get("tokenInAmount", 0) or s.get("tokenOutAmount", 0)))
            val = amount * m_data["price"]
            
            log_now(f"🔍 CHECK: {m_data['symbol']} | Val: ${val:,.0f} | Price: {m_data['price']}")

            # TEST FILTER: 50 $
            if m_data["price"] > 0 and val >= 50:
                log_now(f"🎯 TRIGGER: Sending to Telegram {m_data['symbol']} ${val:,.0f}")
                msg = f"🧪 <b>LIVE TEST</b>\n🪙 <b>Token:</b> {m_data['symbol']}\n💰 <b>Buy:</b> ${val:,.0f}"
                posli_tg_spravu(TG_KANAL_ZAKLAD, msg)

    return "OK", 200

# 🧪 TESTOVACÍ ODKAZ PRE TELEGRAM
@app.route('/test-tg')
def test_tg():
    log_now("🛠️ Manual TG Test triggered...")
    msg = "✅ <b>System check:</b> Ak vidíš túto správu, tvoj bot a kanál sú prepojené správne!"
    posli_tg_spravu(TG_KANAL_ZAKLAD, msg)
    return "Test správa odoslaná! Skontroluj Telegram."

@app.route('/')
def status():
    return "Server is running (Build 6.1.6)"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
