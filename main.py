# build v5.0.8
from flask import Flask, Response, request
import requests
import os
import json
import threading
import time
from datetime import datetime
import openai
from supabase import create_client, Client

app = Flask(__name__)

# 🔐 Kľúče a Nastavenia
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
NASE_API_HESLO = os.environ.get("NASE_API_HESLO", "master_kluc_123")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

# 🤖 Telegram Kľúče
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
    try: requests.post(url, json=payload)
    except: pass

def zisti_dex_info(token_adresa):
    if token_adresa == "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": return "USDC", 1.0, 10000000
    try:
        res = requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{token_adresa}").json()
        if res.get("pairs"):
            p = res["pairs"][0]
            sym = p.get("baseToken", {}).get("symbol", "")
            if not sym or sym.lower() == "unknown": sym = token_adresa[:4].upper()
            return sym, float(p.get("priceUsd", 0)), float(p.get("liquidity", {}).get("usd", 0))
    except: pass
    return token_adresa[:4].upper(), 0.0, 0.0

# ⚙️ 1. MOTOR (Základný kanál)
def lov_velryb():
    rpc_url = "https://mainnet.helius-rpc.com/?api-key=3770f955-3c49-4abc-b2c6-960a7e138ee3"
    target_wallet = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8" 
    while True:
        if not supabase: time.sleep(15); continue
        try:
            sig = requests.post(rpc_url, json={"jsonrpc": "2.0", "id": 1, "method": "getSignaturesForAddress", "params": [target_wallet, {"limit": 1}]}).json()
            if "result" in sig and len(sig["result"]) > 0:
                latest_tx = sig["result"][0]["signature"]
                if not supabase.table('velryby_v2').select("id").eq("transakcia", latest_tx).execute().data:
                    tx_det = requests.post(rpc_url, json={"jsonrpc": "2.0", "id": 2, "method": "getTransaction", "params": [latest_tx, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}]}).json()
                    meta = tx_det.get("result", {}).get("meta", {})
                    pre_b, post_b = meta.get("preTokenBalances", []), meta.get("postTokenBalances", [])
                    
                    for post in post_b:
                        mint = post.get("mint")
                        zostatok_post = post.get("uiTokenAmount", {}).get("uiAmount") or 0
                        if (mint == "So11111111111111111111111111111111111111112" and zostatok_post >= 50) or (mint == "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v" and zostatok_post >= 10000) or zostatok_post > 50000:
                            acc_idx = post.get("accountIndex")
                            zostatok_pre = next((p["uiTokenAmount"]["uiAmount"] for p in pre_b if p.get("accountIndex") == acc_idx), 0) or 0
                            rozdiel = zostatok_post - zostatok_pre
                            
                            if abs(rozdiel) < 1: continue 
                            
                            symbol, cena, likvidita = zisti_dex_info(mint)
                            hodnota_usd = abs(rozdiel) * cena
                            
                            # 🛑 TVRDÝ FILTER: 10 000 $
                            if cena > 0 and hodnota_usd < 10000: continue
                            if cena == 0 and abs(rozdiel) < 500000: continue 
                            
                            akcia = "🟢 BUY" if rozdiel > 0 else "🔴 SELL"
                            riziko_en = "⚠️ High Risk" if likvidita < 10000 else "✅ Safe"
                            profi_data = f"{datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')} | {akcia} | Token: {symbol} | Value: ${hodnota_usd:.2f} | Liquidity: ${likvidita:.2f}"
                            
                            supabase.table('velryby_v2').insert({"transakcia": latest_tx, "token": mint, "suma": abs(rozdiel), "ai_audit": profi_data}).execute()
                            
                            if rozdiel > 0:
                                tg_riziko = "⚠️ Warning, new unverified coin!" if likvidita < 10000 else "✅ Safe (healthy liquidity pool)"
                                tg_sprava = f"🚨 <b>MASSIVE WHALE BUY!</b> 🚨\n\n🪙 <b>Coin:</b> {symbol}\n💸 <b>Invested:</b> ${hodnota_usd:,.0f}\n💧 <b>Safety:</b> {tg_riziko}\n\n📝 <b>Quick Summary:</b>\nA massive whale just bet heavily that {symbol} is going up. If you want to follow their lead, click the link below.\n\n🔗 <a href='https://dexscreener.com/solana/{mint}'>📈 View Chart & Buy Here</a>"
                                posli_tg_spravu(TG_KANAL_ZAKLAD, tg_sprava)
        except: pass
        time.sleep(15)

# 🧠 2. MOTOR (VIP kanál)
def ai_radar():
    while True:
        time.sleep(300) 
        if not supabase or not OPENAI_API_KEY: continue
        try:
            zaznamy = supabase.table('velryby_v2').select("*").order("id", desc=True).limit(50).execute().data
            nakupy = {}
            for z in zaznamy:
                if "🟢" in z.get("ai_audit", ""):
                    t = z["token"]
                    nakupy[t] = nakupy.get(t, []) + [z]
            
            for token, zoznam in nakupy.items():
                if len(zoznam) >= 3:
                    if not supabase.table('signaly').select("id").eq("token", token).execute().data:
                        symbol, _, _ = zisti_dex_info(token)
                        openai.api_key = OPENAI_API_KEY
                        
                        prompt = f"You are a ruthless crypto expert. 3 whales just simultaneously bought the Solana coin {symbol} (each over $10,000). Skip the boring warnings. Answer exactly in this format for Telegram:\n🔥 Opinion: [Your take]\n🎯 Action: [BUY / WATCH / STAY AWAY]\n💡 Reason: [1 short sentence why]"
                        
                        ai_res = openai.chat.completions.create(model="gpt-3.5-turbo", messages=[{"role": "user", "content": prompt}], max_tokens=150)
                        signal_text = ai_res.choices[0].message.content.strip()
                        
                        supabase.table('signaly').insert({"cas": datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'), "token": token, "ai_analyza": f"🚨 VIP SIGNAL [{symbol}]:\n{signal_text}"}).execute()
                        
                        vip_sprava = f"👑 <b>VIP AI SIGNAL: WHALE SWARM!</b> 👑\n\n🪙 <b>Coin:</b> {symbol}\n👀 <b>What's happening:</b> Several whales bought this coin at the exact same time with HUGE volume (+$10k each). The radar detected an anomaly.\n\n🤖 <b>AI Advice:</b>\n{signal_text}\n\n🔗 <a href='https://dexscreener.com/solana/{token}'>📈 View on DexScreener</a>"
                        posli_tg_spravu(TG_KANAL_VIP, vip_sprava)
        except: pass

threading.Thread(target=lov_velryb, daemon=True).start()
threading.Thread(target=ai_radar, daemon=True).start()

# 🌐 WEB API
@app.route('/')
def status():
    if not over_heslo(): return Response(json.dumps({"error": "Unauthorized."}, indent=4).encode('utf-8'), status=401, mimetype='application/json')
    return Response(json.dumps({"api_status": "ONLINE", "mode": "B2C TELEGRAM 10k$ FILTER 🌍"}, indent=4, ensure_ascii=False).encode('utf-8'), mimetype='application/json; charset=utf-8')

@app.route('/historia')
def ukaz_historiu():
    if not over_heslo(): return Response(json.dumps({"error": "Unauthorized."}, indent=4).encode('utf-8'), status=401, mimetype='application/json')
    try:
        res = supabase.table('velryby_v2').select("*").order("id", desc=True).limit(50).execute()
        return Response(json.dumps({"saved_whales": res.data}, indent=4, ensure_ascii=False).encode('utf-8'), mimetype='application/json; charset=utf-8')
    except Exception as e: return Response(json.dumps({"error": str(e)}, indent=4).encode('utf-8'), mimetype='application/json; charset=utf-8')

@app.route('/signaly')
def ukaz_signaly():
    if not over_heslo(): return Response(json.dumps({"error": "Unauthorized."}, indent=4).encode('utf-8'), status=401, mimetype='application/json')
    try:
        res = supabase.table('signaly').select("*").order("id", desc=True).limit(20).execute()
        return Response(json.dumps({"vip_signals": res.data}, indent=4, ensure_ascii=False).encode('utf-8'), mimetype='application/json; charset=utf-8')
    except Exception as e: return Response(json.dumps({"error": str(e)}, indent=4).encode('utf-8'), mimetype='application/json; charset=utf-8')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
