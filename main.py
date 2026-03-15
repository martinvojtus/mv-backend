# build 6.1.3
from flask import Flask, Response, request
import requests
import os
import json
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

def over_heslo():
    return (request.headers.get("X-API-Key") or request.args.get("api_key")) == NASE_API_HESLO

def posli_tg_spravu(kanal, text):
    if not TG_BOT_TOKEN or not kanal: return
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": kanal, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    try: requests.post(url, json=payload, timeout=5)
    except: pass

def get_market_data(mint):
    if not mint: return {"symbol": "ERR", "price": 0, "mc": 0, "liq": 0}
    # Špeciálna cena pre SOL (fallback)
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
    except: pass
    return {"symbol": str(mint)[:4].upper(), "price": 0, "mc": 0, "liq": 0}

@app.route('/webhook', methods=['POST'])
def handle_webhook():
    if not over_heslo(): return "Unauthorized", 401
    data = request.json
    if not data or not isinstance(data, list): return "OK", 200

    for tx in data:
        events = tx.get("events", {}).get("swap", {})
        if not events: continue
        t_in, t_out = events.get("tokenInMint"), events.get("tokenOutMint")
        mint = t_in if t_in != "So11111111111111111111111111111111111111112" else t_out
        if not mint: continue

        m_data = get_market_data(mint)
        if m_data["price"] == 0: continue # Preskočíme nákupy, ktoré nevieme oceniť

        amount = abs(float(events.get("tokenInAmount", 0) or events.get("tokenOutAmount", 0)))
        value_usd = amount * m_data["price"]
        
        if value_usd < 2000: continue

        impact = (value_usd / m_data["mc"] * 100) if m_data["mc"] > 0 else 0
        tx_sig = tx.get("signature")
        
        # Formátovanie auditu pre DB bez emoji, aby sa nerozbilo kódovanie
        audit_str = f"VALUE: ${value_usd:,.0f} | MC: ${m_data['mc']:,.0f} | IMPACT: {impact:.2f}%"
        
        try:
            supabase.table('velryby_v2').insert({"transakcia": tx_sig, "token": mint, "suma": amount, "ai_audit": audit_str}).execute()
        except: pass

        ten_mins_ago = (datetime.utcnow() - timedelta(minutes=10)).strftime('%Y-%m-%dT%H:%M:%SZ')
        recent = supabase.table('velryby_v2').select("ai_audit").eq("token", mint).gt("created_at", ten_mins_ago).execute().data
        total_vol = sum(float(r['ai_audit'].split('$')[1].split(' |')[0].replace(',', '')) for r in recent if '$' in r.get('ai_audit', ''))

        if value_usd >= 50000 or impact >= 1.0 or (total_vol >= 100000 and len(recent) >= 2):
            msg_type = "🐋 SINGLE WHALE" if value_usd >= 50000 else "🔥 HIGH IMPACT"
            if total_vol >= 100000 and value_usd < 50000: msg_type = "🕵️‍♂️ STEALTH ACCUMULATION"

            msg = (f"🚨 <b>{msg_type}</b>\n\n🪙 <b>Token:</b> {m_data['symbol']}\n💰 <b>Buy:</b> ${value_usd:,.0f}\n"
                   f"📊 <b>Impact:</b> {impact:.2f}% of MC\n\n🔗 <a href='https://dexscreener.com/solana/{mint}'>View Chart</a>")
            posli_tg_spravu(TG_KANAL_ZAKLAD, msg)

            if total_vol >= 150000 or (impact >= 2.0 and value_usd > 10000):
                analyze_vip(mint, m_data, value_usd, total_vol, impact, len(recent))
    return "OK", 200

def analyze_vip(mint, m_data, value, total_vol, impact, count):
    if not OPENAI_API_KEY: return
    try:
        openai.api_key = OPENAI_API_KEY
        # Agresívnejší prompt pre AI
        prompt = (f"Analyze {m_data['symbol']} (MC: ${m_data['mc']:,.0f}). Buy: ${value:,.0f}. Total 10m vol: ${total_vol:,.0f}. Impact: {impact:.2f}%. "
                  "Act as a ruthless whale tracker. Use strictly 3 lines: 🔥 Opinion, 🎯 Action, 💡 Reason. Be bold and concise.")
        ai_res = openai.chat.completions.create(model="gpt-3.5-turbo", messages=[{"role": "user", "content": prompt}], max_tokens=100)
        analysis = ai_res.choices[0].message.content.strip()
        
        try: supabase.table('signaly').insert({"token": mint, "ai_analyza": analysis}).execute()
        except: pass

        vip_msg = (f"👑 <b>VIP INSIDER SIGNAL</b> 👑\n\n🪙 <b>Token:</b> {m_data['symbol']}\n💰 <b>Flow:</b> ${total_vol:,.0f}\n\n"
                   f"🤖 <b>AI Intel:</b>\n{analysis}\n\n🔗 <a href='https://dexscreener.com/solana/{mint}'>Trade Now</a>")
        posli_tg_spravu(TG_KANAL_VIP, vip_msg)
    except: pass

@app.route('/')
def status():
    return Response(json.dumps({"status": "ONLINE", "mode": "PRO v6.1.3 ⚡"}, indent=4, ensure_ascii=False), mimetype='application/json; charset=utf-8')

@app.route('/historia')
def ukaz_historiu():
    if not over_heslo(): return "Unauthorized", 401
    res = supabase.table('velryby_v2').select("*").order("id", desc=True).limit(50).execute()
    # Oprava kódovania pre prehliadač
    return Response(json.dumps({"saved_whales": res.data}, indent=4, ensure_ascii=False), mimetype='application/json; charset=utf-8')

@app.route('/signaly')
def ukaz_signaly():
    if not over_heslo(): return "Unauthorized", 401
    res = supabase.table('signaly').select("*").order("id", desc=True).limit(20).execute()
    return Response(json.dumps({"vip_signals": res.data}, indent=4, ensure_ascii=False), mimetype='application/json; charset=utf-8')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
