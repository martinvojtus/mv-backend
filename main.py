# build v5.0.7
from flask import Flask, Response
import requests
import os
import json
import sqlite3
import threading
import time
import openai # 🛑 Novy AI mozog!

app = Flask(__name__)

# 🔑 Tvoj OpenAI kľúč (Zatial nechame prazdny)
OPENAI_API_KEY = "VLOZ_SVOJ_OPENAI_KLUC_TU"

# 🛠️ Inicializacia databazy (Nova verzia so stlpcom ai_audit)
def init_db():
    conn = sqlite3.connect('whales.db')
    conn.execute('CREATE TABLE IF NOT EXISTS velryby_v2 (id INTEGER PRIMARY KEY, transakcia TEXT, token TEXT, suma REAL, ai_audit TEXT)')
    conn.commit()
    conn.close()

init_db()

# 🧠 AI Audítor
def sprav_ai_audit(token_adresa):
    if OPENAI_API_KEY == "VLOZ_SVOJ_OPENAI_KLUC_TU":
        return "🤖 AI čaká na prepojenie (chýba kľúč)"
    
    try:
        openai.api_key = OPENAI_API_KEY
        prompt = f"Analyzuj krypto token s adresou {token_adresa} na sieti Solana. Je to známy token (napr. SOL, USDC) alebo neznámy altcoin? Odpovedz stručne jednou vetou a pridaj odhad rizika."
        
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=60
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"⚠️ Chyba AI: {str(e)}"

# ⚙️ MOTOR NA POZADI
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
                                    
                                    # ⚡ Bleskove zavolanie AI!
                                    ai_vysledok = sprav_ai_audit(mint_adresa)
                                    
                                    conn.execute("INSERT INTO velryby_v2 (transakcia, token, suma, ai_audit) VALUES (?, ?, ?, ?)", (latest_tx, mint_adresa, zostatok, ai_vysledok))
                                    conn.commit()
                conn.close()
        except: pass
        time.sleep(15)

threading.Thread(target=lov_velryb, daemon=True).start()

# 🌐 WEB ROZHRANIE
@app.route('/')
def status():
    return Response(json.dumps({"api_status": "🟢 AI MOTOR BEZI 24/7"}, indent=4, ensure_ascii=False).encode('utf-8'), mimetype='application/json; charset=utf-8')

@app.route('/historia')
def ukaz_historiu():
    try:
        conn = sqlite3.connect('whales.db')
        kurzor = conn.execute("SELECT * FROM velryby_v2 ORDER BY id DESC LIMIT 50")
        zaznamy = [{"id": r[0], "transakcia": r[1], "token": r[2], "suma": r[3], "ai_audit": r[4]} for r in kurzor.fetchall()]
        conn.close()
        return Response(json.dumps({"ulozene_velryby": zaznamy}, indent=4, ensure_ascii=False).encode('utf-8'), mimetype='application/json; charset=utf-8')
    except Exception as e:
        return Response(json.dumps({"chyba": str(e)}, indent=4).encode('utf-8'), mimetype='application/json; charset=utf-8')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
