# build 6.1.0
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
TG_KANAL_ZAKLAD = os.environ.get("TG_KANAL_ZAKLAD", "") # voidadamradar
TG_KANAL_VIP = os.environ.get("TG_KANAL_VIP", "")       # voidadamsignal

supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def over_heslo():
    return (request.headers.get("X-API-Key") or request.args.get("api_key")) == NASE_API_HESLO

def posli_tg_spravu(kanal, text):
    if not TG_BOT_TOKEN or not kanal: return
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": kanal, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    requests.post(url, json=payload)

def get_market_data(mint):
    try:
        res = requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{mint}").json()
        if res.get("pairs"):
            p = res["pairs"][0]
            return {
                "symbol": p.get("baseToken", {}).get("symbol", "Unknown"),
                "price": float(p.get("priceUsd", 0)),
                "mc": float(p.get("fdv", 0) or p.get("marketCap", 0)),
                "liq": float(p.get("liquidity", {}).get("usd", 0))
            }
    except: pass
    return {"symbol": mint[:4].upper(), "price": 0, "mc": 0, "liq": 0}

@app.route('/webhook', methods=['POST'])
def handle_webhook():
    if not over_heslo(): return "Unauthorized", 401
    
    data = request.json
    if not data or not isinstance(data, list): return "OK", 200

    for tx in data:
        events = tx.get("events", {}).get("swap", {})
        if not events: continue

        mint = events.get("tokenInMint") if events.get("tokenInMint") != "So11111111111111111111111111111111111111112" else events.get("tokenOutMint")
        amount = abs(float(events.get("tokenInAmount", 0) or events.get("tokenOutAmount", 0)))
        
        m_data = get_market_data(mint)
        value_usd = amount * m_data["price"]
        
        # Ignorujeme totálny balast pod $2,000, aby sme nepreťažili databázu
        if value_usd < 2000: continue

        impact = (value_usd / m_data["mc"] * 100) if m_data["mc"] > 0 else 0
        tx_sig = tx.get("signature")
        cas_iso = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')

        # 1. ZÁPIS DO DB (všetko podstatné ukladáme na analýzu sčítania)
        supabase.table('velryby_v2').insert({
            "transakcia": tx_sig, 
            "token": mint, 
            "suma": amount, 
            "ai_audit": f"VALUE: ${value_usd:.0f} | IMPACT: {impact:.2f}%"
        }).execute()

        # 2. VÝPOČET AKUMULÁCIE (Posledných 10 minút)
        ten_mins_ago = (datetime.utcnow() - timedelta(minutes=10)).strftime('%Y-%m-%dT%H:%M:%SZ')
        recent_txs = supabase.table('velryby_v2').select("ai_audit").eq("token", mint).gt("created_at", ten_mins_ago).execute().data
        
        total_recent_usd = 0
        for r in recent_txs:
            try: total_recent_usd += float(r['ai_audit'].split('$')[1].split(' |')[0])
            except: pass

        # 🛑 TRIGGERS PRE RADAR (voidadamradar)
        trigger_large = value_usd >= 50000
        trigger_impact = impact >= 1.0
        trigger_stealth = total_recent_usd >= 100000 and len(recent_txs) >= 2

        if trigger_large or trigger_impact or trigger_stealth:
            msg_type = "🐋 SINGLE WHALE" if trigger_large else "🔥 HIGH IMPACT"
            if trigger_stealth and not trigger_large: msg_type = "🕵️‍♂️ STEALTH ACCUMULATION"

            msg = (f"🚨 <b>{msg_type}</b>\n\n"
                   f"🪙 <b>Token:</b> {m_data['symbol']}\n"
                   f"💰 <b>Current Buy:</b> ${value_usd:,.0f}\n"
                   f"📈 <b>10m Volume:</b> ${total_recent_usd:,.0f}\n"
                   f"📊 <b>Impact:</b> {impact:.2f}% of MC\n\n"
                   f"🔗 <a href='https://dexscreener.com/solana/{mint}'>View Chart</a>")
            posli_tg_spravu(TG_KANAL_ZAKLAD, msg)

            # 💎 VIP SIGNÁL (voidadamsignal) - Prísnejšia AI analýza
            if total_recent_usd >= 150000 or (impact >= 2.0 and value_usd > 10000):
                analyze_vip(mint, m_data, value_usd, total_recent_usd, impact, len(recent_txs))

    return "OK", 200

def analyze_vip(mint, m_data, value, total_vol, impact, count):
    openai.api_key = OPENAI_API_KEY
    prompt = (f"Analyze Solana token {m_data['symbol']}. MC: ${m_data['mc']:,.0f}. "
              f"Current move: ${value:,.0f}. Total 10m volume: ${total_vol:,.0f} from {count} transactions. "
              f"Impact: {impact:.2f}%. Is this an insider pump or healthy whale accumulation? "
              "Output in 3 lines: 🔥 Opinion, 🎯 Action, 💡 Reason. No warnings.")
    
    ai_res = openai.chat.completions.create(model="gpt-3.5-turbo", messages=[{"role": "user", "content": prompt}], max_tokens=100)
    analysis = ai_res.choices[0].message.content.strip()

    vip_msg = (f"👑 <b>VIP INSIDER ALERT</b> 👑\n\n"
               f"🪙 <b>Token:</b> {m_data['symbol']} | MC: ${m_data['mc']:,.0f}\n"
               f"🔥 <b>Momentum:</b> {count} buys in 10 mins\n"
               f"💰 <b>Total Flow:</b> ${total_vol:,.0f}\n\n"
               f"🤖 <b>AI Intel:</b>\n<i>{analysis}</i>\n\n"
               f"🔗 <a href='https://dexscreener.com/solana/{mint}'>Trade Now</a>")
    posli_tg_spravu(TG_KANAL_VIP, vip_msg)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
