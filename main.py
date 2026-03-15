# build v1.1
from flask import Flask, Response, request
import requests
import os
import json
import sqlite3
import threading
import time
import openai

app = Flask(__name__)

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
NASE_API_HESLO = os.environ.get("NASE_API_HESLO", "master_kluc_123")

def over_heslo():
    zadane_heslo = request.headers.get("X-API-Key") or request.args.get("api_key")
    return zadane_heslo == NASE_API_HESLO

def init_db():
    conn = sqlite3.connect('whales.db')
    conn.execute('CREATE TABLE IF NOT EXISTS velryby_v2 (id INTEGER PRIMARY KEY, transakcia TEXT, token TEXT, suma REAL, ai_audit TEXT)')
    conn.commit()
    conn.close()

init_db()

def sprav_ai_audit(token_adresa):
    if not OPENAI_API_KEY:
        return "AI Key missing"
        
    # ⚡ Skratka pre zname tokeny (Setri tvoj OpenAI kredit a vyhne sa chybam)
    if token_adresa == "So11111111111111111111111111111111111111112":
        return "Native Solana Token (SOL). Safe."
    if token_adresa == "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v":
        return "USDC Stablecoin. Safe."

    try:
        openai.api_key = OPENAI_API_KEY
        # 🇬🇧 Anglicky prompt s poziadavkou na max 1 vetu
        prompt = f"Analyze Solana token address: {token_adresa}. Is it a known token or an unknown altcoin? Give a 1-sentence risk assessment."
        
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo", 
            messages=[{"role": "user", "content": prompt}], 
            max_tokens=100 # ⬆️ Zvyseny limit
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"AI Error: {str(e)}"

def lov_velryb():
    rpc_url = "https://mainnet.helius-rpc.com/?api-key=3770f955-3c49-4abc-b2c6-960a7e138ee3"
    target_wallet = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8" 
    
    while True:
        try:
            payload_sig = {"jsonrpc": "2.0", "id": 1, "method": "getSignaturesForAddress", "params": [target_wallet, {"limit": 1}]}
            sig = requests.post(rpc_url, json=payload_sig).json()
            
            if "result" in sig and len(sig["result"]) > 0:
                latest_tx = sig["result"][0]["signature"]
                conn = sqlite3.connect('whales.db')
                if not conn.execute("SELECT 1 FROM velryby_v2 WHERE transakcia = ?", (latest_tx,)).fetchone():
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
                                    conn.execute("INSERT INTO velryby_v2 (transakcia, token, suma, ai_audit) VALUES (?, ?, ?, ?)", (latest_tx, mint_adresa, zostatok, ai_vysledok))
                                    conn.commit()
                conn.close()
        except: pass
        time.sleep(15)

threading.Thread(target=lov_velryb, daemon=True).start()

@app.route('/')
def status():
    if not over_heslo():
        return Response(json.dumps({"error": "Unauthorized. Invalid API key."}, indent=4).encode('utf-8'), status=401, mimetype='application/json')
    return Response(json.dumps({"api_status": "ONLINE", "mode": "B2M SECURED"}, indent=4, ensure_ascii=False).encode('utf-8'), mimetype='application/json; charset=utf-8')

@app.route('/historia')
def ukaz_historiu():
    if not over_heslo():
        return Response(json.dumps({"error": "Unauthorized. Invalid API key."}, indent=4).encode('utf-8'), status=401, mimetype='application/json')
    try:
        conn = sqlite3.connect('whales.db')
        kurzor = conn.execute("SELECT * FROM velryby_v2 ORDER BY id DESC LIMIT 50")
        zaznamy = [{"id": r[0], "transakcia": r[1], "token": r[2], "suma": r[3], "ai_audit": r[4]} for r in kurzor.fetchall()]
        conn.close()
        return Response(json.dumps({"ulozene_velryby": zaznamy}, indent=4, ensure_ascii=False).encode('utf-8'), mimetype='application/json; charset=utf-8')
    except Exception as e:
        return Response(json.dumps({"error": str(e)}, indent=4).encode('utf-8'), mimetype='application/json; charset=utf-8')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
