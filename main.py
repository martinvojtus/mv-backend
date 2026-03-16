# build 6.5.2
from flask import Flask, Response, request, render_template_string
import requests
import os
from datetime import datetime
import openai
from supabase import create_client, Client
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__)
# Potrebujeme "vlákno na pozadí", aby Telegram nečakal na pomalú AI
executor = ThreadPoolExecutor(max_workers=2)

# 🔐 Config
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
NASE_API_HESLO = os.environ.get("NASE_API_HESLO", "v0idbot@dam")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "")
TG_KANAL_VIP = os.environ.get("TG_KANAL_VIP", "")

supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>📊 BTC Súkromný Radar</title>
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

def posli_tg_spravu(kanal, text, klavesnica=None):
    if not TG_BOT_TOKEN or not kanal: return
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": kanal, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    if klavesnica:
        payload["reply_markup"] = klavesnica
    try: requests.post(url, json=payload, timeout=5)
    except: pass

def get_macro_data():
    data = {"price": 0, "change_pct": 0, "volume": 0, "btc_dominance": 0, "total_mcap": 0}
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get("https://api.kucoin.com/api/v1/market/stats?symbol=BTC-USDT", headers=headers, timeout=5).json()
        if res.get("code") == "200000" and "data" in res:
            data["price"] = float(res["data"].get("last", 0))
            data["change_pct"] = round(float(res["data"].get("changeRate", 0)) * 100, 2)
            data["volume"] = float(res["data"].get("volValue", 0))
            
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
            f"BTC: ${macro['price']:,.0f} | 24h: {macro['change_pct']}% | "
            f"Vol: ${macro['volume']:,.0f} | Dom: {macro['btc_dominance']}% | "
            f"Cap: ${macro['total_mcap']:,.0f}\n\n"
            "Napíš stručnú, priamu a faktickú analýzu trhu v slovenčine. "
            "Žiadny marketingový slovník, žiadne zbytočné omáčky. "
            "Výstup musí obsahovať presne 3 jasné body s použitím relevantných emoji:\n"
            "1. 🎯 Kľúčové levely (Support/Resistance)\n"
            "2. 🏦 Trhový sentiment\n"
            "3. 💡 Očakávaný vývoj"
        )
        
        ai_res = openai.chat.completions.create(model="gpt-3.5-turbo", messages=[{"role": "user", "content": prompt}], max_tokens=500)
        analysis = ai_res.choices[0].message.content.strip()

        try: supabase.table('signaly').insert({"token": "BTC", "ai_analyza": f"💰 Cena: ${macro['price']:,.0f} | 📈 24h: {macro['change_pct']}%\n\n{analysis}"}).execute()
        except: pass
        
        msg = (f"📊 <b>BTC REPORT</b>\n"
               f"⏱️ {cas_teraz} UTC\n\n"
               f"💰 <b>Cena:</b> ${macro['price']:,.0f}\n"
               f"📈 <b>Zmena (24h):</b> {macro['change_pct']}%\n"
               f"🌊 <b>Objem:</b> ${macro['volume']:,.0f}\n"
               f"👑 <b>Dominancia:</b> {macro['btc_dominance']}%\n"
               f"🌍 <b>Market Cap:</b> ${(macro['total_mcap']/1e12):.2f}T\n\n"
               f"🧠 <b>Analýza:</b>\n{analysis}")
        
        posli_tg_spravu(TG_KANAL_VIP, msg)
    except Exception as e:
        print(f"Chyba AI: {e}", flush=True)

def spusti_radar_proces(chat_id=None):
    """Proces bežiaci na pozadí, aby Telegram nezamrzol"""
    macro = get_macro_data()
    if macro['price'] == 0:
        if chat_id: posli_tg_spravu(chat_id, "❌ API chyba pri sťahovaní dát.")
        return
    
    cas_teraz = datetime.utcnow().strftime('%H:%M:%S')
    tx_id = f"MACRO-{int(datetime.utcnow().timestamp())}"
    audit_str = f"📈 24h: {macro['change_pct']}% | 👑 DOM: {macro['btc_dominance']}%"
    try: supabase.table('velryby_v2').insert({"transakcia": tx_id, "token": "BTC", "suma": macro['price'], "ai_audit": audit_str}).execute()
    except: pass

    analyze_btc(macro, cas_teraz)
    
    # Ak to vyžiadal používateľ v chate, napíšeme mu potvrdenie
    if chat_id:
        posli_tg_spravu(chat_id, "✅ <b>Report úspešne odoslaný</b> do VIP kanála!")

# --- TELEGRAM WEBHOOK A OVLÁDANIE ---

@app.route('/tg-webhook', methods=['POST'])
def handle_tg_webhook():
    data = request.json
    if data and "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"].get("text", "")
        
        # Odošle permanentnú klávesnicu s tlačidlom
        if text in ["/start", "📊 Bleskový Report"]:
            klavesnica = {
                "keyboard": [[{"text": "📊 Bleskový Report"}]],
                "resize_keyboard": True,
                "is_persistent": True
            }
            if text == "/start":
                posli_tg_spravu(chat_id, "👋 Som tvoj osobný Radar Bot. Klikni na tlačidlo nižšie, ak chceš okamžite vygenerovať report.", klavesnica)
            
        # Ak používateľ klikol na tlačidlo, spustí sa proces na pozadí
        if text == "📊 Bleskový Report":
            posli_tg_spravu(chat_id, "⏳ <i>Sťahujem dáta z búrz a generujem AI analýzu...</i>")
            executor.submit(spusti_radar_proces, chat_id)
            
    return "OK", 200

@app.route('/set-webhook')
def set_tg_webhook():
    """Zavolaj túto adresu po nasadení, aby si botovi povedal, kde má počúvať!"""
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/setWebhook?url=https://{request.host}/tg-webhook"
    r = requests.get(url)
    return r.json()

# --- ŠTANDARDNÉ WEBOVÉ CESTY ---

@app.route('/btc-radar', methods=['GET'])
def trigger_btc_radar():
    """Stále funguje aj pre Cron-Job"""
    if not over_heslo(): return "Unauthorized", 401
    executor.submit(spusti_radar_proces)
    return "Radar spustený!", 200

@app.route('/historia')
def ukaz_historiu():
    if not over_heslo(): return "Unauthorized", 401
    res = supabase.table('velryby_v2').select("*").eq("token", "BTC").order("id", desc=True).limit(30).execute()
    def render_whale(item):
        db_cas = item.get('created_at', 'Neznámy čas')[:19].replace('T', ' ')
        return f"""<div class="header-row"><span class="time">⏱️ {db_cas} UTC</span><span class="price">${item.get('suma', 0):,.0f}</span></div><div class="token">🪙 Bitcoin (BTC)</div><div class="audit">{item.get('ai_audit', '')}</div>"""
    return render_template_string(HTML_TEMPLATE, title="📊 BTC Makro História", data=res.data, render_item=render_whale)

@app.route('/signaly')
def ukaz_signaly():
    if not over_heslo(): return "Unauthorized", 401
    res = supabase.table('signaly').select("*").eq("token", "BTC").order("id", desc=True).limit(20).execute()
    def render_signal(item):
        db_cas = item.get('created_at', 'Neznámy čas')[:19].replace('T', ' ')
        return f"""<div class="header-row"><span class="time">⏱️ {db_cas} UTC</span><span class="price">🧠 AI Report</span></div><div class="token">🪙 Bitcoin (BTC)</div><div class="audit">{item.get('ai_analyza', '').replace('\n', '<br>')}</div>"""
    return render_template_string(HTML_TEMPLATE, title="🧠 BTC Signály", data=res.data, render_item=render_signal)

@app.route('/')
def status():
    return Response('{"status": "ONLINE", "mode": "BOT_CONTROL 6.5.2 🎛️"}', mimetype='application/json')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)), threaded=True)
