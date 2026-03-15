# build v6.0
from flask import Flask, Response, request
import requests
import os
import json
from datetime import datetime
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

# 📡 HLAVNÝ WEBHOOK PRIJÍMAČ
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
        
        # 🧮 IMPACT SCORE CALCULATION
        # $$Impact = \frac{Value_{USD}}{MarketCap} \times 100$$
        impact = (value_usd / m_data["mc"] * 100) if m_data["mc"] > 0 else 0

        # 🛑 SMART FILTERS
        # Scenario 1: Heavyweight Whale (>100k)
        # Scenario 2: High Impact (>1% of Market Cap for smaller coins)
        is_whale = value_usd >= 100000
        is_shaker = (m_data["mc"] < 5000000 and impact >= 1.0) # 1% impact on coins under 5M MC

        if is_whale or is_shaker:
            tx_sig = tx.get("signature")
            cas = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
            
            # Save to Supabase
            audit_str = f"{cas} | BUY | Impact: {impact:.2f}% | MC: ${m_data['mc']:,.0f}"
            supabase.table('velryby_v2').insert({"transakcia": tx_sig, "token": mint, "suma": amount, "ai_audit": audit_str}).execute()

            # 📢 TELEGRAM: BASIC CHANNEL
            safety = "✅ Healthy" if m_data["liq"] > 50000 else "⚠️ Low Liquidity"
            msg = f"🚨 <b>WHALE MOVEMENT!</b> 🚨\n\n🪙 <b>Coin:</b> {m_data['symbol']}\n💸 <b>Amount:</b> ${value_usd:,.0f}\n📊 <b>Impact:</b> {impact:.2f}% of MC\n💧 <b>Safety:</b> {safety}\n\n🔗 <a href='https://dexscreener.com/solana/{mint}'>📈 View Chart</a>"
            posli_tg_spravu(TG_KANAL_ZAKLAD, msg)

            # 🧠 AI RADAR: SWARM & STEALTH CHECK
            check_swarm_and_analyze(mint, m_data, value_usd, impact)

    return "OK", 200

def check_swarm_and_analyze(mint, m_data, value_usd, impact):
    # Check last 5 minutes for this token in DB
    recent = supabase.table('velryby_v2').select("*").eq("token", mint).order("id", desc=True).limit(5).execute().data
    
    if len(recent) >= 3: # 🐝 SWARM DETECTED!
        openai.api_key = OPENAI_API_KEY
        prompt = (f"CRYPTO ANALYSIS: Token {m_data['symbol']} (MC: ${m_data['mc']:,.0f}). "
                  f"3+ whales just bought in 5 mins. Current buy: ${value_usd:,.0f} ({impact:.2f}% impact). "
                  "Identify if this is a Swarm, Momentum Ignition or Stealth Accumulation. "
                  "Output strictly in 3 lines: 🔥 Opinion, 🎯 Action (BUY/WATCH), 💡 Reason.")
        
        ai_res = openai.chat.completions.create(model="gpt-3.5-turbo", messages=[{"role": "user", "content": prompt}], max_tokens=150)
        analysis = ai_res.choices[0].message.content.strip()

        vip_msg = (f"👑 <b>VIP AI SIGNAL: SWARM DETECTED!</b> 👑\n\n"
                   f"🪙 <b>Coin:</b> {m_data['symbol']}\n"
                   f"📈 <b>Market Cap:</b> ${m_data['mc']:,.0f}\n"
                   f"🔥 <b>Momentum:</b> High (Cluster buy)\n\n"
                   f"🤖 <b>AI Analysis:</b>\n{analysis}\n\n"
                   f"🔗 <a href='https://dexscreener.com/solana/{mint}'>📈 Trade Now</a>")
        posli_tg_spravu(TG_KANAL_VIP, vip_msg)

# 🌐 API Routes
@app.route('/')
def status():
    return Response(json.dumps({"status": "ONLINE", "mode": "WEBHOOK v6.0 ⚡"}, indent=4).encode('utf-8'), mimetype='application/json')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
