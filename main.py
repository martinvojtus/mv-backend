# build 6.1.8
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
NASE_API_HESLO = os.environ.get("NASE_API_HESLO", "v0idbot@dam")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "")
TG_KANAL_ZAKLAD = os.environ.get("TG_KANAL_ZAKLAD", "") 
TG_KANAL_VIP = os.environ.get("TG_KANAL_VIP", "")

supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def log_now(msg):
    print(msg, flush=True)
    sys.stdout.flush()

def over_heslo():
    return (request.args.get("api_key")) == NASE_API_HESLO

def posli_tg_spravu(kanal, text):
    if not TG_BOT_TOKEN or not kanal: return
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": kanal, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    try: requests.post(url, json=payload, timeout=5)
    except: pass

def get_market_data(mint):
    if not mint: return {"symbol": "ERR", "price": 0, "mc": 1}
    try:
        res = requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{mint}", timeout=5).json()
        if res.get("pairs"):
            p = res["pairs"][0]
            return {
                "symbol": p.get("baseToken", {}).get("symbol", "UNK"),
                "price": float(p.get("priceUsd", 0)),
                "mc": float(p.get("fdv", 0) or p.get("marketCap", 1))
            }
    except: pass
    return {"symbol": str(mint)[:4].upper(), "price": 0, "mc": 1}

@app.route('/webhook', methods=['POST'])
def handle_webhook():
    if not over_heslo(): return "Unauthorized", 401
    data = request.json
    log_now(f"📡 WEBHOOK START: Received {len(data) if data else 0} txs")

    for tx in data:
        # Hľadáme priamo v tokenTransfers (najspoľahlivejší spôsob)
        transfers = tx.get("tokenTransfers", [])
        
        for t in transfers:
            mint = t.get("mint")
            # Ignorujeme čistý SOL, chceme vidieť altcoiny/memecoiny
            if not mint or mint == "So11111111111111111111111111111111111111112":
                continue
                
            amount = float(t.get("tokenAmount", 0))
            if amount <= 0: continue

            m_data = get_market_data(mint)
            val = amount * m_data["price"]
            
            log_now(f"🔍 CHECK: {m_data['symbol']} | Val: ${val:,.0f} | Price: {m_data['price']}")

            if m_data["price"] > 0 and val >= 50: # 🧪 TEST FILTER 50$
                impact = (val / m_data["mc"] * 100) if m_data["mc"] > 0 else 0
                tx_sig = tx.get("signature")
                audit_str = f"VALUE: ${val:,.0f} | MC: ${m_data['mc']:,.0f} | IMPACT: {impact:.2f}%"
                
                try: supabase.table('velryby_v2').insert({"transakcia": tx_sig, "token": mint, "suma": amount, "ai_audit": audit_str}).execute()
                except: pass

                msg = f"🧪 <b>LIVE TEST</b>\n🪙 <b>Token:</b> {m_data['symbol']}\n💰 <b>Value:</b> ${val:,.0f}"
                posli_tg_spravu(TG_KANAL_ZAKLAD, msg)

    return "OK", 200

@app.route('/test-tg')
def test_tg():
    posli_tg_spravu(TG_KANAL_ZAKLAD, "✅ <b>System check:</b> Bot a kanál sú prepojené!")
    return "Test správa odoslaná!"

@app.route('/historia')
def ukaz_historiu():
    if not over_heslo(): return "Unauthorized", 401
    res = supabase.table('velryby_v2').select("*").order("id", desc=True).limit(50).execute()
    return Response(json.dumps({"saved_whales": res.data}, indent=4, ensure_ascii=False), mimetype='application/json; charset=utf-8')

@app.route('/signaly')
def ukaz_signaly():
    if not over_heslo(): return "Unauthorized", 401
    res = supabase.table('signaly').select("*").order("id", desc=True).limit(20).execute()
    return Response(json.dumps({"vip_signals": res.data}, indent=4, ensure_ascii=False), mimetype='application/json; charset=utf-8')

@app.route('/')
def status():
    return Response(json.dumps({"status": "ONLINE", "mode": "FIXED_PARSER 6.1.8 ⚡"}, indent=4), mimetype='application/json')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
