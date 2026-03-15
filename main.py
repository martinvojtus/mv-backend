# build 6.3.4
from flask import Flask, Response, request, render_template_string
import requests
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import openai
from supabase import create_client, Client

app = Flask(__name__)
# 🚦 Fronta: Zvládne max 5 analýz naraz
executor = ThreadPoolExecutor(max_workers=5)

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
    <title>🐋 VIP Radar Dashboard</title>
    <style>
        body { background-color: #0d1117; color: #c9d1d9; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; padding: 20px; max-width: 800px; margin: auto; }
        h1 { color: #ffffff; border-bottom: 2px solid #30363d; padding-bottom: 10px; }
        .card { background-color: #161b22; border: 1px solid #30363d; border-radius: 10px; padding: 15px; margin-bottom: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
        .token { color: #58a6ff; font-weight: bold; font-size: 1.1em; }
        .audit { margin-top: 10px; padding: 10px; background-color: #0d1117; border-radius: 5px; font-family: monospace; font-size: 0.95em; border-left: 3px solid #30363d; }
        .header-row { display: flex; justify-content: space-between; margin-bottom: 8px; font-size: 0.9em; }
        .time { color: #8b949e; }
        a { color: #58a6ff; text-decoration: none; }
        a:hover { text-decoration: underline; }
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

def analyze_vip(mint, m_data, value, total_vol, impact, cas_teraz, action_str):
    if not OPENAI_API_KEY: return
    try:
        openai.api_key = OPENAI_API_KEY
        prompt = (f"Analyze {m_data['symbol']} (MC: ${m_data['mc']:,.0f}). Action: {action_str}. Amount: ${value:,.0f}. Vol: ${total_vol:,.0f}. Impact: {impact:.2f}%. "
                  "Use 3 lines: 🔥 Macro Opinion, 🎯 Smart Money Action, 💡 Deep Reason. Be bold.")
        ai_res = openai.chat.completions.create(model="gpt-3.5-turbo", messages=[{"role": "user", "content": prompt}], max_tokens=100)
        analysis = ai_res.choices[0].message.content.strip()
        
        try: supabase.table('signaly').insert({"token": mint, "ai_analyza": f"{action_str} 🪙 {m_data['symbol']} | {analysis}"}).execute()
        except: pass
        
        vip_msg = (f"👑 <b>SMART MONEY SIGNAL</b> 👑\n"
                   f"⏱️ <b>Time:</b> {cas_teraz} UTC\n\n"
                   f"🪙 <b>Asset:</b> {m_data['symbol']}\n{action_str}\n💰 <b>Inflow:</b> ${total_vol:,.0f}\n📊 <b>MC Impact:</b> {impact:.2f}%\n\n"
                   f"🤖 <b>AI Intel:</b>\n{analysis}\n\n🔗 <a href='https://dexscreener.com/solana/{mint}'>View Asset</a>")
        posli_tg_spravu(TG_KANAL_VIP, vip_msg)
    except: pass

def spracuj_transakcie_na_pozadi(filtroidne_data):
    cas_teraz = datetime.utcnow().strftime('%H:%M:%S')
    
    for tx in filtroidne_data:
        fee_payer = tx.get("feePayer")
        transfers = tx.get("tokenTransfers", [])
        
        for t in transfers:
            mint = t.get("mint")
            if not mint or mint == "So11111111111111111111111111111111111111112" or mint == "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v":
                continue
                
            amount = float(t.get("tokenAmount", 0))
            if amount <= 0: continue

            m_data = get_market_data(mint)
            val = amount * m_data["price"]

            # Ukladáme všetko nad 4 500 $
            if m_data["price"] == 0 or val < 4500: continue

            impact = (val / m_data["mc"] * 100) if m_data["mc"] > 0 else 0
            tx_sig = tx.get("signature")
            
            # 🟢 BUY vs 🔴 SELL Detekcia
            action_text = "🔄 SWAP"
            action_html = "🔄 SWAP"
            if t.get("toUserAccount") == fee_payer:
                action_text = "🟢 BUY"
                action_html = "🟢 <b>BUY</b>"
            elif t.get("fromUserAccount") == fee_payer:
                action_text = "🔴 SELL"
                action_html = "🔴 <b>SELL</b>"
            
            audit_str = f"{action_text} | 🪙 {m_data['symbol']} | VALUE: ${val:,.0f} | MC: ${m_data['mc']:,.0f} | IMPACT: {impact:.2f}%"
            
            try: supabase.table('velryby_v2').insert({"transakcia": tx_sig, "token": mint, "suma": amount, "ai_audit": audit_str}).execute()
            except: pass

            ten_mins_ago = (datetime.utcnow() - timedelta(minutes=10)).strftime('%Y-%m-%dT%H:%M:%SZ')
            recent = supabase.table('velryby_v2').select("ai_audit").eq("token", mint).gt("created_at", ten_mins_ago).execute().data
            total_vol = sum(float(r['ai_audit'].split('VALUE: $')[1].split(' |')[0].replace(',', '')) for r in recent if 'VALUE: $' in r.get('ai_audit', ''))

            # Telegram Alert: Pípa od 15k $ vyššie
            if val >= 15000 or (total_vol >= 30000 and len(recent) >= 2):
                msg_type = "🐋 WHALE ALERT"
                msg = (f"🚨 <b>{msg_type}</b>\n"
                       f"⏱️ <b>Time:</b> {cas_teraz} UTC\n\n"
                       f"🪙 <b>Asset:</b> {m_data['symbol']}\n{action_html}\n💰 <b>Value:</b> ${val:,.0f}\n"
                       f"📈 <b>MC Impact:</b> {impact:.2f}%\n\n🔗 <a href='https://dexscreener.com/solana/{mint}'>View Chart</a>")
                posli_tg_spravu(TG_KANAL_ZAKLAD, msg)

                # VIP Alert: Pípa od 30k $ vyššie
                if total_vol >= 50000 or val > 30000:
                    analyze_vip(mint, m_data, val, total_vol, impact, cas_teraz, action_html)

# 🛡️ Vyhadzovač: Skontroluje aj čistý SOL! (Limit ~30 SOL alebo 4500 USDC)
def je_velka_ryba(tx):
    # 1. Kontrola čistého SOL (Helius ho posiela v lamportoch: 1 SOL = 1 000 000 000)
    for nt in tx.get("nativeTransfers", []):
        if float(nt.get("amount", 0)) >= 30000000000: return True
        
    # 2. Kontrola tokenov (USDC, wSOL)
    for t in tx.get("tokenTransfers", []):
        mint = t.get("mint")
        amount = float(t.get("tokenAmount", 0))
        if mint == "So11111111111111111111111111111111111111112" and amount >= 30: return True
        if mint == "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v" and amount >= 4500: return True
    return False

@app.route('/webhook', methods=['POST'])
def handle_webhook():
    if not over_heslo(): return "Unauthorized", 401
    data = request.json
    if data and isinstance(data, list):
        silne_transakcie = [tx for tx in data if je_velka_ryba(tx)]
        if silne_transakcie:
            executor.submit(spracuj_transakcie_na_pozadi, silne_transakcie)
    return "OK", 200

@app.route('/test-tg')
def test_tg():
    cas_teraz = datetime.utcnow().strftime('%H:%M:%S UTC')
    posli_tg_spravu(TG_KANAL_ZAKLAD, f"✅ <b>System check</b>\n⏱️ <b>Time:</b> {cas_teraz}\nVyhadzovač je nastavený na min. 30 SOL. Čakáme na pohyb! 🚀")
    return "Test správa odoslaná!"

@app.route('/historia')
def ukaz_historiu():
    if not over_heslo(): return "Unauthorized", 401
    res = supabase.table('velryby_v2').select("*").order("id", desc=True).limit(50).execute()
    
    def render_whale(item):
        db_cas = item.get('created_at', 'Neznámy čas')[:19].replace('T', ' ')
        audit = item.get('ai_audit', '')
        
        return f"""
        <div class="header-row">
            <span class="time">⏱️ {db_cas} UTC</span>
        </div>
        <div>🆔 TX ID: {item.get('id')}</div>
        <div>🔗 <a href="https://dexscreener.com/solana/{item.get('token')}" target="_blank" class="token">{item.get('token')[:8]}...</a></div>
        <div class="audit">{audit}</div>
        """
    
    return render_template_string(HTML_TEMPLATE, title="🐋 Úlovky (História)", data=res.data, render_item=render_whale)

@app.route('/signaly')
def ukaz_signaly():
    if not over_heslo(): return "Unauthorized", 401
    res = supabase.table('signaly').select("*").order("id", desc=True).limit(20).execute()
    
    def render_signal(item):
        db_cas = item.get('created_at', 'Neznámy čas')[:19].replace('T', ' ')
        return f"""
        <div class="header-row">
            <span class="time">⏱️ {db_cas} UTC</span>
        </div>
        <div>🆔 Signal ID: {item.get('id')}</div>
        <div>🔗 <a href="https://dexscreener.com/solana/{item.get('token')}" target="_blank" class="token">{item.get('token')[:8]}...</a></div>
        <div class="audit">{item.get('ai_analyza', '').replace('\n', '<br>')}</div>
        """
        
    return render_template_string(HTML_TEMPLATE, title="👑 VIP AI Signály", data=res.data, render_item=render_signal)

@app.route('/')
def status():
    return Response('{"status": "ONLINE", "mode": "SMART_DETECT 6.3.4 🔴🟢"}', mimetype='application/json')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)), threaded=True)
