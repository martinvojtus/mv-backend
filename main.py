# build v1.7
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
        je_to_velryba = False # 🛑 Nas novy filter
        
        if "postTokenBalances" in meta:
            for token in meta["postTokenBalances"]:
                mint_adresa = token.get("mint")
                zostatok = token["uiTokenAmount"]["uiAmount"]
                
                if not zostatok: continue
                
                # 🧮 LOGIKA PRE TRUST SCORE A VELRYBY
                skore = 50
                riziko = "Stredne"
                
                # Zlaty standard 1: Wrapped SOL
                if mint_adresa == "So11111111111111111111111111111111111111112":
                    skore = 100
                    riziko = "Ziadne (SOL)"
                    if zostatok >= 50: je_to_velryba = True # 50 SOL je zhruba $10,000+
                        
                # Zlaty standard 2: USDC (Stablecoin)
                elif mint_adresa == "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v":
                    skore = 100
                    riziko = "Ziadne (USDC)"
                    if zostatok >= 10000: je_to_velryba = True # $10,000
                    
                # Hype/Memecoin s obrovskym mnozstvom
                elif zostatok > 1000000:
                    skore = 20
                    riziko = "Vysoke (Hype/Rug)"
                else:
                    skore = 65
                    riziko = "Mierne"
                    
                zmeny_tokenov.append({
                    "token_adresa": mint_adresa,
                    "zostatok": zostatok,
                    "audit": {"skore_bezpecnosti": skore, "riziko": riziko}
                })
        
        # ⚖️ ROZHODOVACÍ STROM FILTRA
        if not je_to_velryba:
            odpoved = {
                "api_status": "🟡 CAKAM NA VELRYBU", 
                "filter": "Nastaveny na > $10,000", 
                "transakcia": latest_tx, 
                "sprava": "Posledna transakcia je len drobny sum."
            }
        else:
            odpoved = {
                "api_status": "🟢 ONLINE - OMNI ORACLE",
                "typ_signalu": "SMART_MONEY_TRACKER 🐋",
                "transakcia": latest_tx,
                "detegovane_aktiva": zmeny_tokenov
            }
        
        # 🧹 FORMATOVANIE A OPRAVA EMOJIS (UTF-8)
        krasny_json = json.dumps(odpoved, indent=4, ensure_ascii=False)
        return Response(krasny_json.encode('utf-8'), mimetype='application/json; charset=utf-8')
        
    except Exception as e:
        chyba = {"api_status": "🔴 CHYBA SERVERA", "detail": str(e)}
        return Response(json.dumps(chyba, indent=4).encode('utf-8'), mimetype='application/json; charset=utf-8')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
