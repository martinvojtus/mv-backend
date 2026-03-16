# build 6.4.5
from flask import Flask, Response, request, render_template_string
import requests
import os
from datetime import datetime
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

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>👑 BTC Macro Dashboard</title>
    <style>
        body { background-color: #0d1117; color: #c9d1d9; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; padding: 20px; max-width: 800px; margin: auto; }
        h1 { color: #ffffff; border-bottom: 2px solid #30363d; padding-bottom: 10px; }
        .card { background-color: #161b22; border: 1px solid #30363d; border-radius: 10px; padding: 15px; margin-bottom: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
        .token { color: #f7931a; font-weight: bold; font-size: 1.2em; }
        .audit { margin-top: 10px; padding: 10px; background-color: #0d1117; border-radius: 5px; font-family: monospace; font-size: 0.95em; border-left: 3px solid #f7931a; line-height: 1.5; }
        .header-row { display: flex; justify-content: space-between; margin-bottom: 8px; font-size: 0.9em; }
        .time { color: #8b949e; }
        .price { color: #3fb950; font-weight: bold; font-size: 1.1em; }
    </style>
</head>
<body>
    <h1>{{ title }}</h1>
    {% for item in data %}
    <div class="card">
        {{ render_item(item) | safe }}
    </div>
    {% endfor %}
</body>
</html>
"""

def over_heslo():
    return (request.args.get("api_key")) == NASE_API_HESLO

def posli_tg_spravu(kanal, text):
    if not TG_BOT_TOKEN or not kanal: return
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": kanal, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    try: requests.post(url, json=payload, timeout=5)
    except: pass

def get_macro_data():
    data = {
        "price": 0, "change_pct": 0, "volume": 0, 
        "btc_dominance": 0, "total_mcap": 0
    }
    try:
        # 🌐 KuCoin pre presnú cenu BTC
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get("https://api.kucoin.com/api/v1/market/stats?symbol=BTC-USDT", headers=headers, timeout=5).json()
        if res.get("code") == "200000" and "data" in res:
            data["price"] = float(res["data"].get("last", 0))
            data["change_pct"] = round(float(res["data"].get("changeRate", 0)) * 100, 2)
            data["volume"] = float(res["data"].get("volValue", 0))
            
        # 🌐 CoinGecko pre Global Macro údaje (Dominancia a Market Cap)
        cg = requests.get("https://api.coingecko.com/api/v3/global", timeout=5).json()
        if "data" in cg:
            data["btc_dominance"] = round(cg["data"]["market_cap_percentage"].get("btc", 0), 2)
            data["total_mcap"] = cg["data"]["total_market_cap"].get("usd", 0)
    except Exception as e:
        print(f"API Chyba: {e}", flush=True)
    return data

def analyze_btc(macro, cas_teraz):
    if not OPENAI_API_KEY: return
    try:
        openai.api_key = OPENAI_API_KEY
        prompt = (
            f"BTC Price: ${macro['price']:,.0f} | 24h Change: {macro['change_pct']}% | "
            f"24h Vol: ${macro['volume']:,.0f} | BTC Dominance: {macro['btc_dominance']}% | "
            f"Global Market Cap: ${macro['total_mcap']:,.0f}\n\n"
            "Act as a top-tier institutional crypto analyst. Write STRICTLY IN ENGLISH.\n"
            "Provide two sections separated exactly by '===SPLIT==='.\n\n"
            "Section 1: 2 short, engaging English sentences summarizing the macro vibe and hinting at the next move. Do not use words like 'Teaser' or 'Section'.\n"
            "===SPLIT===\n"
            "Section 2: 4 concise bullet points in English using emojis:\n"
            "1. 🎯 Key Levels (Support/Resistance)\n"
            "2. 📊 Probability (Next move odds in %)\n"
            "3. 🏦 Institutional & ETF Flows (Estimate current sentiment based on volume and dominance)\n"
            "4. 💡 Action (Clear macro plan)"
        )
        
        ai_res = openai.chat.completions.create(
            model="gpt-3.5-turbo", 
            messages=[{"role": "user", "content": prompt}], 
            max_tokens=400
        )
        
        ai_text = ai_res.choices[0].message.content.strip()
        
        # Očistenie a rozdelenie
        if "===SPLIT===" in ai_text:
            parts = ai_text.split("===SPLIT===")
            free_text = parts[0].replace("Section 1:", "").strip()
            vip_text = parts[1].replace("Section 2:", "").strip()
        else:
            free_text = "Market analysis processing..."
            vip_text = ai_text

        # 💾 Uloženie do DB
        try: supabase.table('signaly').insert({"token": "BTC", "ai_analyza": f"💰 Price: ${macro['price']:,.0f} | 📈 24h: {macro['change_pct']}%\n\n{vip_text}"}).execute()
        except: pass
        
        # 💎 VIP Telegram Správa (Teraz s Makro dátami)
        vip_msg = (f"👑 <b>BTC MACRO UPDATE</b> 👑\n"
                   f"⏱️ <b>Time:</b> {cas_teraz} UTC\n\n"
                   f"🪙 <b>Asset:</b> Bitcoin (BTC)\n"
                   f"💵 <b>Price:</b> ${macro['price']:,.0f}\n"
                   f"📊 <b>24h Change:</b> {macro['change_pct']}%\n"
                   f"📈 <b>BTC Dominance:</b> {macro['btc_dominance']}%\n"
                   f"🌍 <b>Global Cap:</b> ${(macro['total_mcap']/1e12):.2f}T\n\n"
                   f"🧠 <b>PRO INTEL:</b>\n{vip_text}")
        posli_tg_spravu(TG_KANAL_VIP, vip_msg)

        # 🎣 Free Telegram Správa
        free_msg = (f"🌐 <b>MARKET PULSE</b>\n"
                    f"⏱️ <b>Time:</b> {cas_teraz} UTC\n\n"
                    f"🪙 <b>Bitcoin:</b> ${macro['price']:,.0f}\n"
                    f"📈 <b>24h Trend:</b> {macro['change_pct']}%\n"
                    f"🌊 <b>Volume:</b> ${macro['volume']:,.0f}\n\n"
                    f"👀 <b>Market Hint:</b>\n{free_text}\n\n"
                    f"👑 <i>Exact levels, probabilities, and ETF tracking available in VIP.</i>")
        posli_tg_spravu(TG_KANAL_ZAKLAD, free_msg)

    except Exception as e:
        print(f"Chyba AI: {e}", flush=True)

@app.route('/btc-radar', methods=['GET'])
def trigger_btc_radar():
    if not over_heslo(): return "Unauthorized", 401
    
    macro = get_macro_data()
    if macro['price'] == 0: return "API Error", 500
    
    cas_teraz = datetime.utcnow().strftime('%H:%M:%S')
    
    tx_id = f"MACRO-{int(datetime.utcnow().timestamp())}"
    audit_str = f"📈 24h: {macro['change_pct']}% | 👑 DOM: {macro['btc_dominance']}% | 🌍 CAP: ${(macro['total_mcap']/1e12):.2f}T"
    try: supabase.table('velryby_v2').insert({"transakcia": tx_id, "token": "BTC", "suma": macro['price'], "ai_audit": audit_str}).execute()
    except: pass

    analyze_btc(macro, cas_teraz)

    return f"Success: Analysed at ${macro['price']:,.0f}", 200

@app.route('/historia')
def ukaz_historiu():
    if not over_heslo(): return "Unauthorized", 401
    res = supabase.table('velryby_v2').select("*").eq("token", "BTC").order("id", desc=True).limit(30).execute()
    
    def render_whale(item):
        db_cas = item.get('created_at', 'Neznámy čas')[:19].replace('T', ' ')
        cena = item.get('suma', 0)
        return f"""
        <div class="header-row">
            <span class="time">⏱️ {db_cas} UTC</span>
            <span class="price">${cena:,.0f}</span>
        </div>
        <div class="token">🪙 Bitcoin (BTC)</div>
        <div class="audit">{item.get('ai_audit', '')}</div>
        """
    return render_template_string(HTML_TEMPLATE, title="📊 BTC Makro História", data=res.data, render_item=render_whale)

@app.route('/signaly')
def ukaz_signaly():
    if not over_heslo(): return "Unauthorized", 401
    res = supabase.table('signaly').select("*").eq("token", "BTC").order("id", desc=True).limit(20).execute()
    
    def render_signal(item):
        db_cas = item.get('created_at', 'Neznámy čas')[:19].replace('T', ' ')
        return f"""
        <div class="header-row">
            <span class="time">⏱️ {db_cas} UTC</span>
            <span class="price">👑 VIP AI Report</span>
        </div>
        <div class="token">🪙 Bitcoin (BTC)</div>
        <div class="audit">{item.get('ai_analyza', '').replace('\n', '<br>')}</div>
        """
    return render_template_string(HTML_TEMPLATE, title="👑 VIP BTC Signály", data=res.data, render_item=render_signal)

@app.route('/')
def status():
    return Response('{"status": "ONLINE", "mode": "GLOBAL_MACRO 6.4.5 🌍"}', mimetype='application/json')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)), threaded=True)
