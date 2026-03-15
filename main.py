# build 6.1.5
from flask import Flask, Response, request
import requests
import os
import json
import sys # Pridané pre okamžitý výpis logov
from datetime import datetime, timedelta
import openai
from supabase import create_client, Client

app = Flask(__name__)

# 🔐 Config
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
NASE_API_HESLO = os.environ.get("NASE_API_HESLO", "master_kluc_123")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "")
TG_KANAL_ZAKLAD = os.environ.get("TG_KANAL_ZAKLAD", "") 
TG_KANAL_VIP = os.environ.get("TG_KANAL_VIP", "")

supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Pomocná funkcia na logovanie, ktoré hneď uvidíš v Renderi
def log_now(msg):
    print(msg, flush=True)
    sys.stdout.flush()

def over_heslo():
    return (request.headers.get("X-API-Key") or request.args.get("api_key")) == NASE_API_HESLO

def posli_tg_spravu(kanal, text):
    if not TG_BOT_TOKEN or not kanal: return
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": kanal, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    try: requests.post(url, json=payload, timeout=5)
    except Exception as e: log_now(f"❌ TG Error: {e}")

def get_market_data(mint):
    if not mint: return {"symbol": "ERR", "price": 0, "mc": 0, "liq": 0}
    if mint == "So11111111111111111111111111111111111111112":
        return {"symbol": "SOL", "price": 150.0, "mc": 70000000000, "liq": 1000000000}
    try:
        res = requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{mint}", timeout=5).json()
        if res.get("pairs"):
            p = res["pairs"][0]
            return {
                "symbol": p.get("baseToken", {}).get("symbol", "Unknown"),
                "price": float(p.get("priceUsd", 0)),
                "mc": float(p.get("fdv", 0) or p.get("marketCap", 0)),
                "liq": float(p.get("liquidity", {}).get("usd", 0))
            }
    except Exception as e: log_now(f"❌ Dex Error: {e}")
    return {"symbol": str(mint)[:4].upper(), "price": 0, "mc": 0, "liq": 0}

@app.route('/webhook', methods=['POST'])
def handle_webhook():
    if not over_heslo(): return "Unauthorized", 401
    data = request.json
    
    log_now(f"📡 WEBHOOK IN: Received {len(data) if data else 0} txs")

    if not data or not isinstance(data, list): return "OK", 200

    for tx in data:
        events = tx.get("events", {}).get("swap", {})
        if not events: continue
        t_in, t_out = events.get("tokenInMint"), events.get("tokenOutMint")
        mint = t_in if t_in != "So11111111111111111111111111111111111111112" else t_out
        if not mint: continue

        m_data = get_market_data(mint)
        amount = abs(float(events.get("tokenInAmount", 0) or events.get("tokenOutAmount", 0)))
        val = amount * m_data["price"]
        
        # TOTO UVIDÍŠ V LOGOCH
        log_now(f"🔍 CHECK: {m_data['symbol']} | Val: ${val:,.0f} | Price: {m_data['price']}")

        # DOČASNÝ TESTOVACÍ FILTER (100 $), aby sme videli pohyb
        if m_data["price"] == 0 or val < 100: continue

        impact = (val / m_data["mc"] * 100) if m_data["mc"] > 0 else 0
        tx_sig = tx.get("signature")
        audit_str = f"VALUE: ${val:,.0f} | MC: ${m_data['mc']:,.0f} | IMPACT: {impact:.2f}%"
        
        try:
            supabase.table('velryby_v2').insert({"transakcia": tx_sig, "token": mint, "suma": amount, "ai_audit": audit_str}).execute()
            log_now(f"✅ DB SAVED: {m_data['symbol']} ${val:,.0f}")
        except Exception as e: log_now(f"❌ DB Error: {e}")

        # Prah pre správy (znížený na 100 pre test)
        if val >= 100:
            msg = f"🧪 <b>TEST ALERT</b>\n🪙 <b>Token:</b> {m_data['symbol']}\n💰 <b>Buy:</b> ${val:,.0f}"
            posli_tg_spravu(TG_KANAL_ZAKLAD, msg)

    return "OK", 200

@app.route('/')
def status():
    log_now("🌐 Status page hit")
    return Response(json.dumps({"status": "ONLINE", "mode": "TEST_LOGGING 6.1.5"}, indent=4, ensure_ascii=False), mimetype='application/json; charset=utf-8')

@app.route('/historia')
def ukaz_historiu():
    if not over_heslo(): return "Unauthorized", 401
    res = supabase.table('velryby_v2').select("*").order("id", desc=True).limit(50).execute()
    return Response(json.dumps({"saved_whales": res.data}, indent=4, ensure_ascii=False), mimetype='application/json; charset=utf-8')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
