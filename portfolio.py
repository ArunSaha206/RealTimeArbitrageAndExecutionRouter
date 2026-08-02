class Portfolio:
    def __init__(self, starting_cash):
        self.cash = starting_cash
        self.positions = {}  # Maps symbol -> {'qty': int, 'entry_price': float, 'entry_time': datetime, 'entry_idx': int}
        self.trade_log = []
        
    def get_position(self, symbol):
        """Returns current holding details for a symbol."""
        return self.positions.get(symbol, {'qty': 0, 'entry_price': 0.0})

    def get_equity(self, symbol, current_price):
        """Calculates total portfolio value (cash + holding value)."""
        pos = self.get_position(symbol)
        return self.cash + (pos['qty'] * current_price)

    def buy(self, symbol, current_price, current_dt, bar_index, strategy_name, mode, fixed_qty):
        """Calculates sizing and executes a buy order if cash is available."""
        # Calculate how many shares to buy
        if mode == "ALLIN":
            qty = int(self.cash // current_price) if current_price > 0 else 0
        else:
            qty = fixed_qty

        cost = qty * current_price
        
        if qty > 0 and cost <= self.cash:
            self.cash -= cost
            self.positions[symbol] = {
                'qty': qty,
                'entry_price': current_price,
                'entry_time': current_dt,
                'entry_idx': bar_index
            }
            return True, qty
            
        return False, 0

    def sell(self, symbol, current_price, current_dt, bar_index, strategy_name):
        """Sells a current position, updates cash, and logs the trade."""
        pos = self.positions.get(symbol)
        if not pos or pos['qty'] <= 0:
            return False
            
        sale_revenue = pos['qty'] * current_price
        self.cash += sale_revenue
        
        pnl_dollars = (current_price - pos['entry_price']) * pos['qty']
        pnl_pct = ((current_price - pos['entry_price']) / pos['entry_price']) * 100
        bars_held = bar_index - pos['entry_idx']
        
        # Log the trade dynamically
        self.trade_log.append({
            "symbol": symbol,
            "strategy_used": strategy_name,
            "entry_time": pos['entry_time'],
            "exit_time": current_dt,
            "entry_price": pos['entry_price'],
            "exit_price": current_price,
            "quantity": pos['qty'],
            "pnl_dollars": pnl_dollars,
            "pnl_pct": pnl_pct,
            "bars_held": bars_held
        })
        
        # Clear position
        self.positions.pop(symbol)
        return True