# build v1.2
from flask import Flask, jsonify
import requests
import os

app = Flask(__name__)

@app.route('/')
def whale_tracker():
    rpc_url = "VLOZ_SVOJ_HELIUS_URL_TU"
    
    # Adresa Raydium Liquidity (Epicentrum obchodovania na Solane)
    target_wallet = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8" 
    
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getSignaturesForAddress",
        "params": [target_wallet, {"limit": 1}]
    }
    
    response = requests.post(rpc_url, json=payload).json()
    
    if "result" in response and len(response["result"]) > 0:
        latest_tx = response["result"][0]["signature"]
        return jsonify({"status": "Lov uspesny 🎯", "najnovsia_transakcia": latest_tx})
    
    return jsonify({"status": "Cakame na data ⏳", "detail": response})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
