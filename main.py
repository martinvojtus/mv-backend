from flask import Flask
import requests
import os

app = Flask(__name__)

@app.route('/')
def check_solana():
    rpc_url = "https://mainnet.helius-rpc.com/?api-key=3770f955-3c49-4abc-b2c6-960a7e138ee3"
    payload = {"jsonrpc": "2.0", "id": 1, "method": "getHealth"}
    response = requests.post(rpc_url, json=payload)
    return f"⚡ Status Solany: {response.json()}"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
