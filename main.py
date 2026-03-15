# build v1.6
from flask import Flask, Response
import requests
import os
import json

app = Flask(__name__)

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
        
        if "postTokenBalances" in meta:
            for token in meta["postTokenBalances"]:
                mint_adresa = token.get("mint")
                zostatok = token["uiTokenAmount"]["uiAmount"]
                
                # 🧮 MATEMATIKA A LOGIKA PRE TRUST SCORE
                skore = 50
                riziko = "Stredne"
                
                # Pravidlo 1: Je to Wrapped SOL? (Zlaty standard)
                if mint_adresa == "So11111111111111111111111111111111111111112":
                    skore = 100
                    riziko = "Ziadne (Nativny Token)"
                # Pravidlo 2: Obrovske mnozstva casto znamenaju shitcoin/memecoin
                elif zostatok and zostatok > 1000000:
                    skore = 20
                    riziko = "Vysoke (Hype/Rug moznost)"
                # Pravidlo 3: Neznamy token so standardnym mnozstvom
                else:
                    skore = 65
                    riziko = "Mierne (Nutny hlbsi audit)"
                    
                trust_score = {
                    "skore_bezpecnosti_0_100": skore,
                    "riziko_podvodu": riziko
                }
                
                zmeny_tokenov.append({
                    "token_adresa": mint_adresa,
                    "zostatok": zostatok,
                    "audit": trust_score
                })
        
        # Vystupne data
        vystup = {
            "api_status": "🟢 ONLINE - OMNI ORACLE",
            "typ_signalu": "SMART_MONEY_TRACKER",
            "transakcia": latest_tx,
            "detegovane_aktiva": zmeny_tokenov
        }
        
        # 🧹 FORMATOVANIE PRE KRASNY VZHLAD
        krasny_json = json.dumps(vystup, indent=4, ensure_ascii=False)
        return Response(krasny_json, mimetype='application/json')
        
    except Exception as e:
        chyba = {"api_status": "🔴 CHYBA SERVERA", "detail": str(e)}
        return Response(json.dumps(chyba, indent=4), mimetype='application/json')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
