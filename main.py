# build v5.0.6
from flask import Flask, Response
import requests
import os
import json
import sqlite3
import threading
import time

app = Flask(__name__)

# 🛠️ Inicializacia databazy
def init_db():
    conn = sqlite3.connect('whales.db')
    conn.execute('CREATE TABLE IF NOT EXISTS ulovene_velryby (id INTEGER PRIMARY KEY, transakcia TEXT, token TEXT, suma REAL)')
    conn.commit()
    conn.close()

init_db()

# ⚙️ MOTOR NA POZADI (Autonomny lov)
def lov_velryb():
    rpc_url = "https://mainnet.helius-rpc.com/?api-key=3770f955-3c49-4abc-b2c6-960a7e138ee3"
    target_wallet = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8" 
    
    while True:
        try:
            payload_sig = {"jsonrpc": "2.0", "id": 1, "method": "getSignaturesForAddress", "params": [target_wallet, {"limit": 1}]}
            sig_response = requests.post(rpc_url, json=payload_sig).json()
            
            if "result" in sig_response and len(sig_response["result"]) > 0:
                latest_tx = sig_response["result"][0]["signature"]
                
                # 🛑 Kontrola duplicity (aby sme neulozili tu istu transakciu 10x)
                conn = sqlite3.connect('whales.db')
                kurzor = conn.execute("SELECT * FROM ulovene_velryby WHERE transakcia = ?", (latest_tx,))
                existuje = kurzor.fetchone()
                
                if not existuje:
                    payload_tx = {"jsonrpc": "2.0", "id": 2, "method": "getTransaction", "params": [latest_tx, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}]}
                    tx_detail = requests.post(rpc_url, json=payload_tx).json()
                    
                    if "result" in tx_detail and tx_detail["result"] and "meta" in tx_detail["result"]:
                        meta = tx_detail["result"]["meta"]
                        if "postTokenBalances" in meta:
                            for token in meta["postTokenBalances"]:
                                mint_adresa = token.get("mint")
                                zostatok = token["uiTokenAmount"]["uiAmount"]
                                
                                if not zostatok: continue
                                
                                je_to_velryba = False
                                if mint_adresa == "So11111111111111111111111111111111111111112" and zostatok >= 50:
                                    je_to_velryba = True
                                elif mint_adresa == "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v" and zostatok >= 10000:
                                    je_to_velryba = True
                                    
                                if je_to_velryba:
                                    conn.execute("INSERT INTO ulovene_velryby (transakcia, token, suma) VALUES (?, ?, ?)", (latest_tx, mint_adresa, zostatok))
                                    conn.commit()
                conn.close()
        except Exception as e:
            pass # Ignorujeme vypadky siete a pokracujeme dalej
            
        time.sleep(15) # ⏳ Pauza 15 sekund, aby nas Helius nezablokoval za spamovanie

# 🚀 Spustenie motora v samostatnom vlakne hned pri starte servera
vlakno = threading.Thread(target=lov_velryb, daemon=True)
vlakno.start()

# 🌐 WEB ROZHRANIE
@app.route('/')
def status():
    odpoved = {"api_status": "🟢 MOTOR BEZI NA POZADI 24/7", "sprava": "Prejdi na /historia pre zobrazenie ulovkov."}
    return Response(json.dumps(odpoved, indent=4, ensure_ascii=False).encode('utf-8'), mimetype='application/json; charset=utf-8')

@app.route('/historia')
def ukaz_historiu():
    try:
        conn = sqlite3.connect('whales.db')
        kurzor = conn.execute("SELECT * FROM ulovene_velryby ORDER BY id DESC LIMIT 50")
        zaznamy = [{"id": row[0], "transakcia": row[1], "token": row[2], "suma": row[3]} for row in kurzor.fetchall()]
        conn.close()
        return Response(json.dumps({"ulozene_velryby": zaznamy}, indent=4, ensure_ascii=False).encode('utf-8'), mimetype='application/json; charset=utf-8')
    except Exception as e:
        return Response(json.dumps({"chyba": "Chyba databazy", "detail": str(e)}, indent=4).encode('utf-8'), mimetype='application/json; charset=utf-8')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
