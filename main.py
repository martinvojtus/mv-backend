# build 6.1.4
# ... (všetky importy ostávajú)

@app.route('/webhook', methods=['POST'])
def handle_webhook():
    if not over_heslo(): return "Unauthorized", 401
    data = request.json
    
    # Heartbeat log - uvidíš v Renderi, že Helius komunikuje
    print(f"📡 Webhook received at {datetime.utcnow()} - Transactions: {len(data) if data else 0}")

    if not data or not isinstance(data, list): return "OK", 200

    for tx in data:
        events = tx.get("events", {}).get("swap", {})
        if not events: continue
        
        t_in, t_out = events.get("tokenInMint"), events.get("tokenOutMint")
        mint = t_in if t_in != "So11111111111111111111111111111111111111112" else t_out
        if not mint: continue

        m_data = get_market_data(mint)
        
        # LOGOVANIE PRE DEBUG: Ak vidíš toto v logoch, ale nie v TG, filter je moc prísny
        amount = abs(float(events.get("tokenInAmount", 0) or events.get("tokenOutAmount", 0)))
        val = amount * m_data["price"]
        print(f"🔍 Checking: {m_data['symbol']} | Value: ${val:,.0f} | Price: {m_data['price']}")

        if m_data["price"] == 0: continue
        if val < 2000: continue
        
        # ... (zvyšok kódu ostáva rovnaký ako 6.1.3)
    return "OK", 200

# ... (zvyšok kódu)
