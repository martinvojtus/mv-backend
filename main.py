# build v5.0.4
from flask import Flask, Response
import requests
import os
import json
import sqlite3

app = Flask(__name__)

# 🛠️ Vytvorenie databazy
def init_db():
    conn = sqlite3.connect('whales.db')
    conn.execute('CREATE TABLE IF NOT EXISTS ulovene_velryby (id INTEGER PRIMARY KEY, transakcia TEXT, token TEXT, suma REAL)')
    conn.commit()
    conn.close()

init_db()

@app.route('/')
def whale_tracker():
    rpc_url = "https://mainnet.helius-rpc.com/?api-key=3770f955-3c49-4abc-b2c6-960a7e138ee3"
    target_wallet = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8" 
    
    try:
        payload_sig = {"jsonrpc": "2.0", "id": 1, "method": "getSignaturesForAddress", "params": [target_wallet, {"limit": 1}]}
        sig_response = requests.post(rpc_url, json=payload_sig).json()
        latest_tx = sig_response["result"][0]["signature"]
        
        payload_tx = {"jsonrpc": "2.0", "id": 2, "method": "getTransaction", "params": [latest_tx, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}]}
        tx_detail = requests.post(rpc_url, json=payload_tx).json()
        
        meta = tx_detail["result"]["meta"]
        zmeny_tokenov = []
        je_to_velryba = False
        
        if "postTokenBalances" in meta:
            for token in meta["postTokenBalances"]:
                mint_adresa = token.get("mint")
                zostatok = token["uiTokenAmount"]["uiAmount"]
                
                if not zostatok: continue
                
                skore, riziko = 50, "Mierne"
                
                if mint_adresa == "So11111111111111111111111111111111111111112" and zostatok >= 50:
                    skore, riziko, je_to_velryba = 100, "Ziadne (SOL)", True
                elif mint_adresa == "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v" and zostatok >= 10000:
                    skore, riziko, je_to_velryba = 100, "Ziadne (USDC)", True
                elif zostatok > 1000000:
                    skore, riziko = 20, "Vysoke (Hype/Rug)"
                    
                zmeny_tokenov.append({"token_adresa": mint_adresa, "zostatok": zostatok, "audit": {"skore": skore, "riziko": riziko}})
                
                # 💾 Ulozenie do databazy, ak sme chytili velrybu
                if je_to_velryba:
                    conn = sqlite3.connect('whales.db')
                    conn.execute("INSERT INTO ulovene_velryby (transakcia, token, suma) VALUES (?, ?, ?)", (latest_tx, mint_adresa, zostatok))
                    conn.commit()
                    conn.close()
        
        if not je_to_velryba:
            odpoved = {"api_status": "🟡 CAKAM NA VELRYBU", "transakcia": latest_tx}
        else:
            odpoved = {"api_status": "🟢 ULOZENE DO DATABAZY", "transakcia": latest_tx, "aktiva": zmeny_tokenov}
        
        return Response(json.dumps(odpoved, indent=4, ensure_ascii=False).encode('utf-8'), mimetype='application/json; charset=utf-8')
        
    except Exception as e:
        return Response(json.dumps({"chyba": str(e)}, indent=4).encode('utf-8'), mimetype='application/json; charset=utf-8')

# 📜 Novy endpoint na zobrazenie historie
@app.route('/historia')
def ukaz_historiu():
    try:
        conn = sqlite3.connect('whales.db')
        kurzor = conn.execute("SELECT * FROM ulovene_velryby ORDER BY id DESC LIMIT 20")
        zaznamy = [{"id": row[0], "transakcia": row[1], "token": row[2], "suma": row[3]} for row in kurzor.fetchall()]
        conn.close()
        return Response(json.dumps({"ulozene_velryby": zaznamy}, indent=4, ensure_ascii=False).encode('utf-8'), mimetype='application/json; charset=utf-8')
    except Exception as e:
        return Response(json.dumps({"chyba": "Databaza je zatial prazdna alebo nastal problem.", "detail": str(e)}, indent=4).encode('utf-8'), mimetype='application/json; charset=utf-8')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
