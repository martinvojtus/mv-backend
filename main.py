# build 6.4.0
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

# 🎨 HTML Šablóna (Prispôsobená na BTC)
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

def get_btc_data():
    try:
        # 📈 Bezplatné Binance API pre presné dáta
        res = requests.get("https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT", timeout=5).json()
        return {
            "price": float(res.get("lastPrice", 0)),
            "change_pct": float(res.get("priceChangePercent", 0)),
            "volume": float(res.get("quoteVolume", 0)) # Objem v USDT
        }
    except:
        return None

def analyze_btc(btc_data, cas_teraz):
    if not OPENAI_API_KEY: return
    try:
        openai.api_key = OPENAI_API_KEY
        prompt = (f"Bitcoin is currently at ${btc_data['price']:,.2f}. 24h Change: {btc_data['change_pct']}%. 24h Volume: ${btc_data['volume']:,.0f}. "
                  "Act as a senior macro crypto analyst for a VIP fund. Write a concise, punchy 3-line update: 🔥 Macro Trend, 🎯 Key Level to Watch, 💡 Institutional Sentiment. No fluff.")
        ai_res = openai.chat.completions.create(model="gpt-3.5-turbo", messages=[{"role": "user", "content": prompt}], max_tokens=120)
        analysis = ai_res.choices[0].message.content.strip()
        
        # Uloženie do VIP tabuľky
        try: supabase.table('signaly').insert({"token": "BTC", "ai_analyza": f"💰 Cena: ${btc_data['price']:,.0f} | 📈 24h: {btc_data['change_pct']}%\n\n{analysis}"}).execute()
        except: pass
        
        # VIP Telegram Správa
        vip_msg = (f"👑 <b>BTC MACRO UPDATE</b> 👑\n"
                   f"⏱️ <b>Time:</b> {cas_teraz} UTC\n\n"
                   f"🪙 <b>Asset:</b> Bitcoin (BTC)\n"
                   f"💵 <b>Price:</b> ${btc_data['price']:,.0f}\n"
                   f"📊 <b>24h Change:</b> {btc_data['change_pct']}%\n"
                   f"🌊 <b>24h Volume:</b> ${btc_data['volume']:,.0f}\n\n"
                   f"🤖 <b>AI Intel:</b>\n{analysis}")
        posli_tg_spravu(TG_KANAL_VIP, vip_msg)
    except: pass

@app.route('/btc-radar', methods=['GET'])
def trigger_btc_radar():
    """Tento endpoint zavoláme, keď chceme analýzu (napr. raz za 4 hodiny)"""
    if not over_heslo(): return "Unauthorized", 401
    
    btc = get_btc_data()
    if not btc: return "Chyba API", 500
    
    cas_teraz = datetime.utcnow().strftime('%H:%M:%S')
    
    # 1. Uložíme základný záznam do histórie
    tx_id = f"BTC-MACRO-{int(datetime.utcnow().timestamp())}"
    audit_str = f"📈 24h Zmena: {btc['change_pct']}% | 🌊 24h Objem: ${btc['volume']:,.0f}"
    try: supabase.table('velryby_v2').insert({"transakcia": tx_id, "token": "BTC", "suma": btc['price'], "ai_audit": audit_str}).execute()
    except: pass

    # 2. Spustíme AI analýzu a pošleme VIP Report
    analyze_btc(btc, cas_teraz)

    # 3. Pošleme info aj do základného free kanála (ako lákadlo)
    free_msg = (f"🌐 <b>MARKET PULSE</b>\n"
                f"⏱️ <b>Time:</b> {cas_teraz} UTC\n\n"
                f"🪙 <b>Bitcoin:</b> ${btc['price']:,.0f}\n"
                f"📈 <b>24h Trend:</b> {btc['change_pct']}%\n\n"
                f"👑 <i>Hĺbková AI analýza trendu a kľúčových levelov bola práve odoslaná do VIP kanála.</i>")
    posli_tg_spravu(TG_KANAL_ZAKLAD, free_msg)

    return f"BTC Analyzovaný pri cene ${btc['price']}", 200

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
    return Response('{"status": "ONLINE", "mode": "BTC_MACRO_VIP 6.4.0 🪙"}', mimetype='application/json')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)), threaded=True)
