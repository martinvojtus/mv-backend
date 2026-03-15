# build 6.2.0
from flask import Flask, Response, request
import requests
import os
import json
import sys
import threading
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

def spracuj_transakcie_na_pozadi(data):
    """Táto funkcia beží na pozadí a neblokuje server"""
    for tx in data:
        transfers = tx.get("tokenTransfers", [])
        for t in transfers:
            mint = t.get("mint")
            if not mint or mint == "So11111111111111111111111111111111111111112":
                continue
                
            amount = float(t.get("tokenAmount", 0))
            if amount <= 0: continue

            m_data = get_market_data(mint)
            val = amount * m_data["price"]

            if m_data["price"] == 0 or val < 2000: continue

            impact = (val / m_data["mc"] * 100) if m_data["mc"] > 0 else 0
            tx_sig = tx.get("signature")
            audit_str = f"VALUE: ${val:,.0f} | MC: ${m_data['mc']:,.0f} | IMPACT: {impact:.2f}%"
            
            try: supabase.table('velryby_v2').insert({"transakcia": tx_sig, "token": mint, "suma": amount, "ai_audit": audit_str}).execute()
            except: pass

            ten_mins_ago = (datetime.utcnow() - timedelta(minutes=10)).strftime('%Y-%m-%dT%H:%M:%SZ')
            recent = supabase.table('velryby_v2').select("ai_audit").eq("token", mint).gt("created_at", ten_mins_ago).execute().data
            total_vol = sum(float(r['ai_audit'].split('$')[1].split(' |')[0].replace(',', '')) for r in recent if '$' in r.get('ai_audit', ''))

            if val >= 50000 or impact >= 1.0 or (total_vol >= 100000 and len(recent) >= 2):
                msg_type = "🐋 SINGLE WHALE" if val >= 50000 else "🔥 HIGH IMPACT"
                if total_vol >= 100000 and val < 50000: msg_type = "🕵️‍♂️ STEALTH ACCUMULATION"

                msg = (f"🚨 <b>{msg_type}</b>\n\n🪙 <b>Token:</b> {m_data['symbol']}\n💰 <b>Buy:</b> ${val:,.0f}\n"
                       f"📊 <b>Impact:</b> {impact:.2f}% of MC\n\n🔗 <a href='https://dexscreener.com/solana/{mint}'>View Chart</a>")
                posli_tg_spravu(TG_KANAL_ZAKLAD, msg)

                if total_vol >= 150000 or (impact >= 2.0 and val > 10000):
                    analyze_vip(mint, m_data, val, total_vol, impact, len(recent))

def analyze_vip(mint, m_data, value, total_vol, impact, count):
    if not OPENAI_API_KEY: return
    try:
        openai.api_key = OPENAI_API_KEY
        prompt = (f"Analyze {m_data['symbol']} (MC: ${m_data['mc']:,.0f}). Buy: ${value:,.0f}. Vol: ${total_vol:,.0f}. Impact: {impact:.2f}%. "
                  "Act as a ruthless whale tracker. Use 3 lines: 🔥 Opinion, 🎯 Action, 💡 Reason. Be bold.")
        ai_res = openai.chat.completions.create(model="gpt-3.5-turbo", messages=[{"role": "user", "content": prompt}], max_tokens=100)
        analysis = ai_res.choices[0].message.content.strip()
        
        try: supabase.table('signaly').insert({"token": mint, "ai_analyza": analysis}).execute()
        except: pass
        
        vip_msg = (f"👑 <b>VIP INSIDER SIGNAL</b> 👑\n\n🪙 <b>Token:</b> {m_data['symbol']}\n💰 <b>Flow:</b> ${total_vol:,.0f}\n\n"
                   f"🤖 <b>AI Intel:</b>\n{analysis}\n\n🔗 <a href='https://dexscreener.com/solana/{mint}'>Trade Now</a>")
        posli_tg_spravu(TG_KANAL_VIP, vip_msg)
    except: pass

@app.route('/webhook', methods=['POST'])
def handle_webhook():
    if not over_heslo(): return "Unauthorized", 401
    data = request.json
    
    # Okamžite odpálime spracovanie na pozadí, aby sme neblokovali server!
    if data and isinstance(data, list):
        threading.Thread(target=spracuj_transakcie_na_pozadi, args=(data,)).start()

    # Helius dostane OK okamžite za 0.01 sekundy
    return "OK", 200

@app.route('/test-tg')
def test_tg():
    posli_tg_spravu(TG_KANAL_ZAKLAD, "✅ <b>System check:</b> Bot a kanál sú prepojené!")
    return "Test správa odoslaná! Skontroluj Telegram."

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
    return Response(json.dumps({"status": "ONLINE", "mode": "ASYNC_PRO 6.2.0 ⚡"}, indent=4), mimetype='application/json')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
