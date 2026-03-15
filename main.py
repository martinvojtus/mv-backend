# build v1.3
from flask import Flask, Response, request
import requests
import os
import json
import threading
import time
from datetime import datetime
from supabase import create_client, Client

app = Flask(__name__)

# 🔐 Kľúče
NASE_API_HESLO = os.environ.get("NASE_API_HESLO", "master_kluc_123")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

# ☁️ Pripojenie databázy
supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# 🛡️ Ochrana heslom
def over_heslo():
    zadane_heslo = request.headers.get("X-API-Key") or request.args.get("api_key")
    return zadane_heslo == NASE_API_HESLO

# 📊 Bezplatná DexScreener Analýza (Názov, Cena, Likvidita)
def zisti_dex_info(token_adresa):
    if token_adresa == "So11111111111111111111111111111111111111112": return "SOL", 0, 10000000
    if token_adresa == "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": return "USDC", 1, 10000000
    try:
        res = requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{token_adresa}").json()
        if res.get("pairs"):
            p = res["pairs"][0]
            return p.get("baseToken", {}).get("symbol", "Neznámy"), float(p.get("priceUsd", 0)), float(p.get("liquidity", {}).get("usd", 0))
    except: pass
    return "Neznámy", 0.0, 0.0

# ⚙️ Vylepšený motor na lov veľrýb
def lov_velryb():
    rpc_url = "https://mainnet.helius-rpc.com/?api-key=3770f955-3c49-4abc-b2c6-960a7e138ee3"
    target_wallet = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8" 
    
    while True:
        if not supabase:
            time.sleep(15)
            continue
            
        try:
            payload_sig = {"jsonrpc": "2.0", "id": 1, "method": "getSignaturesForAddress", "params": [target_wallet, {"limit": 1}]}
            sig = requests.post(rpc_url, json=payload_sig).json()
            
            if "result" in sig and len(sig["result"]) > 0:
                latest_tx = sig["result"][0]["signature"]
                
                # Kontrola duplicity
                existuje = supabase.table('velryby_v2').select("*").eq("transakcia", latest_tx).execute()
                
                if not existuje.data:
                    tx_det = requests.post(rpc_url, json={"jsonrpc": "2.0", "id": 2, "method": "getTransaction", "params": [latest_tx, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}]}).json()
                    
                    if "result" in tx_det and tx_det["result"] and "meta" in tx_det["result"]:
                        meta = tx_det["result"]["meta"]
                        pre_b = meta.get("preTokenBalances", [])
                        post_b = meta.get("postTokenBalances", [])
                        
                        for post in post_b:
                            mint = post.get("mint")
                            zostatok_post = post["uiTokenAmount"]["uiAmount"] or 0
                            
                            # Filtrujeme len relevantné pohyby
                            if (mint == "So11111111111111111111111111111111111111112" and zostatok_post >= 50) or (mint == "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v" and zostatok_post >= 10000) or zostatok_post > 50000:
                                
                                account_index = post.get("accountIndex")
                                zostatok_pre = next((p["uiTokenAmount"]["uiAmount"] for p in pre_b if p.get("accountIndex") == account_index), 0) or 0
                                
                                rozdiel = zostatok_post - zostatok_pre
                                if abs(rozdiel) < 1: continue 
                                
                                # 🟢/🔴 Nákup alebo Predaj
                                akcia = "🟢 NÁKUP" if rozdiel > 0 else "🔴 PREDAJ"
                                
                                # 💵 Hodnota a Riziko
                                symbol, cena, likvidita = zisti_dex_info(mint)
                                hodnota_usd = abs(rozdiel) * cena
                                riziko = "⚠️ Vysoké" if likvidita < 10000 else "✅ Nízke"
                                cas = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
                                
                                # 📦 Zabalenie do stĺpca ai_audit
                                profi_data = f"{cas} | {akcia} | Minca: {symbol} | Hodnota: ${hodnota_usd:.2f} | Likvidita: ${likvidita:.2f} ({riziko})"
                                
                                supabase.table('velryby_v2').insert({"transakcia": latest_tx, "token": mint, "suma": abs(rozdiel), "ai_audit": profi_data}).execute()
        except: pass
        time.sleep(15)

threading.Thread(target=lov_velryb, daemon=True).start()

# 🌐 API Rozhranie
@app.route('/')
def status():
    if not over_heslo(): return Response(json.dumps({"error": "Unauthorized. Invalid API key."}, indent=4).encode('utf-8'), status=401, mimetype='application/json')
    return Response(json.dumps({"api_status": "ONLINE", "mode": "B2M PREMIUM 📊"}, indent=4, ensure_ascii=False).encode('utf-8'), mimetype='application/json; charset=utf-8')

@app.route('/historia')
def ukaz_historiu():
    if not over_heslo(): return Response(json.dumps({"error": "Unauthorized. Invalid API key."}, indent=4).encode('utf-8'), status=401, mimetype='application/json')
    try:
        if not supabase: return Response(json.dumps({"error": "Supabase not configured."}, indent=4).encode('utf-8'), mimetype='application/json')
        response = supabase.table('velryby_v2').select("*").order("id", desc=True).limit(50).execute()
        return Response(json.dumps({"ulozene_velryby": response.data}, indent=4, ensure_ascii=False).encode('utf-8'), mimetype='application/json; charset=utf-8')
    except Exception as e:
        return Response(json.dumps({"error": str(e)}, indent=4).encode('utf-8'), mimetype='application/json; charset=utf-8')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
