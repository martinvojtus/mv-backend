# build v1.4
from flask import Flask, jsonify
import requests
import os

app = Flask(__name__)

@app.route('/')
def whale_tracker():
    rpc_url = "https://mainnet.helius-rpc.com/?api-key=3770f955-3c49-4abc-b2c6-960a7e138ee3"
    target_wallet = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8" 
    
    # Krok 1: Ziskame podpis (cislo blocku)
    payload_sig = {"jsonrpc": "2.0", "id": 1, "method": "getSignaturesForAddress", "params": [target_wallet, {"limit": 1}]}
    sig_response = requests.post(rpc_url, json=payload_sig).json()
    
    if "result" in sig_response and len(sig_response["result"]) > 0:
        latest_tx = sig_response["result"][0]["signature"]
        
        # Krok 2: Rozsifrujeme detaily
        payload_tx = {"jsonrpc": "2.0", "id": 2, "method": "getTransaction", "params": [latest_tx, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}]}
        tx_detail = requests.post(rpc_url, json=payload_tx).json()
        
        # Krok 3: Extrakcia cistej "Alfy" (len dolezite data)
        try:
            meta = tx_detail["result"]["meta"]
            poplatok = meta["fee"] / 10**9 # Prevod na SOL
            
            zmeny_tokenov = []
            if "postTokenBalances" in meta:
                for token in meta["postTokenBalances"]:
                    zmeny_tokenov.append({
                        "majitel": token.get("owner"),
                        "token_adresa": token.get("mint"),
                        "konecny_zostatok": token["uiTokenAmount"]["uiAmount"]
                    })
                    
            return jsonify({
                "status": "Alfa najdena 💎", 
                "podpis_transakcie": latest_tx,
                "poplatok_za_siet_SOL": poplatok,
                "pohyb_tokenov": zmeny_tokenov
            })
        except Exception as e:
            return jsonify({"status": "Chyba pri analyze ⚠️", "detail": str(e)})
            
    return jsonify({"status": "Cakame na data ⏳"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
