# build v1.5
from flask import Flask, jsonify
import requests
import os

app = Flask(__name__)

@app.route('/')
def whale_tracker():
    rpc_url = "https://mainnet.helius-rpc.com/?api-key=3770f955-3c49-4abc-b2c6-960a7e138ee3"
    target_wallet = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8" 
    
    payload_sig = {"jsonrpc": "2.0", "id": 1, "method": "getSignaturesForAddress", "params": [target_wallet, {"limit": 1}]}
    
    try:
        sig_response = requests.post(rpc_url, json=payload_sig).json()
        latest_tx = sig_response["result"][0]["signature"]
        
        payload_tx = {"jsonrpc": "2.0", "id": 2, "method": "getTransaction", "params": [latest_tx, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}]}
        tx_detail = requests.post(rpc_url, json=payload_tx).json()
        
        meta = tx_detail["result"]["meta"]
        zmeny_tokenov = []
        
        if "postTokenBalances" in meta:
            for token in meta["postTokenBalances"]:
                mint_adresa = token.get("mint")
                
                # 🧠 TU BUDUJEME NAŠU ALFU PRE BOTOV
                # Zatial pripravujeme strukturu pre AI / Heuristicku analyzu
                trust_score = {
                    "riziko_podvodu": "Analyzujem...",
                    "je_mint_uzamknuty": "Nezname",
                    "skore_bezpecnosti_0_100": 0
                }
                
                zmeny_tokenov.append({
                    "token_adresa": mint_adresa,
                    "zostatok": token["uiTokenAmount"]["uiAmount"],
                    "audit": trust_score
                })
                
        return jsonify({
            "api_status": "🟢 ONLINE - OMNI ORACLE",
            "typ_signalu": "SMART_MONEY_TRACKER",
            "transakcia": latest_tx,
            "detegovane_aktiva": zmeny_tokenov
        })
        
    except Exception as e:
        return jsonify({"api_status": "🔴 CHYBA SERVERA", "detail": str(e)})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
