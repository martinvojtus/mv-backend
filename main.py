# build v1.2
from flask import Flask, Response, request
import requests
import os
import json
import threading
import time
import openai
from supabase import create_client, Client

app = Flask(__name__)

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
NASE_API_HESLO = os.environ.get("NASE_API_HESLO", "master_kluc_123")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def over_heslo():
    zadane_heslo = request.headers.get("X-API-Key") or request.args.get("api_key")
    return zadane_heslo == NASE_API_HESLO

def sprav_ai_audit(token_adresa):
    if not OPENAI_API_KEY: return "AI Key missing"
    if token_adresa == "So11111111111111111111111111111111111111112": return "Native Solana Token (SOL). Safe."
    if token_adresa == "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": return "USDC Stablecoin. Safe."
    try:
        openai.api_key = OPENAI_API_KEY
        prompt = f"Analyze Solana token address: {token_adresa}. Is it a known token or an unknown altcoin? Give a 1-sentence risk assessment."
        response = openai.chat.completions.create(model="gpt-3.5-turbo", messages=[{"role": "user", "content": prompt}], max_tokens=100)
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"AI Error: {str(e)}"

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
                
                existuje = supabase.table('velryby_v2').select("*").eq("transakcia", latest_tx).execute()
                
                if not existuje.data:
                    tx_det = requests.post(rpc_url, json={"jsonrpc": "2.0", "id": 2, "method": "getTransaction", "params": [latest_tx, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}]}).json()
                    if "result" in tx_det and tx_det["result"] and "meta" in tx_det["result"]:
                        meta = tx_det["result"]["meta"]
                        if "postTokenBalances" in meta:
                            for token in meta["postTokenBalances"]:
                                mint_adresa = token.get("mint")
                                zostatok = token["uiTokenAmount"]["uiAmount"]
                                if not zostatok: continue
                                if (mint_adresa == "So11111111111111111111111111111111111111112" and zostatok >= 50) or (mint_adresa == "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v" and zostatok >= 10000):
                                    ai_vysledok = sprav_ai_audit(mint_adresa)
                                    supabase.table('velryby_v2').insert({"transakcia": latest_tx, "token": mint_adresa, "suma": zostatok, "ai_audit": ai_vysledok}).execute()
        except: pass
        time.sleep(15)

threading.Thread(target=lov_velryb, daemon=True).start()

@app.route('/')
def status():
    if not over_heslo(): return Response(json.dumps({"error": "Unauthorized. Invalid API key."}, indent=4).encode('utf-8'), status=401, mimetype='application/json')
    return Response(json.dumps({"api_status": "ONLINE", "mode": "B2M SECURED + SUPABASE ☁️"}, indent=4, ensure_ascii=False).encode('utf-8'), mimetype='application/json; charset=utf-8')

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
