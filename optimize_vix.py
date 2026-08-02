# ISSUE WHEN HAVING MULTIPLE STRATEGIES IN CONTROL CENTER WITH TESTING, KNOWN POINTED OUT BY CLAUDE

import optuna
import logging
import sys

# Import your backtest engine runner
from backtest import run_backtest  # Adjust import based on your actual backtest file name

# Suppress excessive logging during optimization loops if desired
optuna.logging.set_verbosity(optuna.logging.WARN)

def objective(trial):
    divisor = trial.suggest_float("divisor", 8.0, 25.0)
    exponent = trial.suggest_float("exponent", 1.0, 3.5)
    
    print(f"\n[Trial {trial.number}] Testing -> Divisor: {divisor:.2f}, Exponent: {exponent:.2f}")
    
    try:
        from strategies.FiveMinute.Support import M5vixsupport
        M5vixsupport.DEFAULT_DIVISOR = divisor
        M5vixsupport.DEFAULT_EXPONENT = exponent
        M5vixsupport._VIX_DAILY_CACHE.clear()

        results = run_backtest() 
        
        # Check total trades executed to prevent 0-trade dead configurations
        total_trades = results.get("total_trades", 0)
        if total_trades < 10:  # Arbitrary threshold: if it barely traded, it's useless
            print(f"[Trial {trial.number}] Pruned: Insufficient trades executed ({total_trades})")
            raise optuna.TrialPruned()
            
        win_rate = results.get("win_rate", 0.0)
        print(f"[Trial {trial.number}] Result -> Win Rate: {win_rate:.2f}%")
        return win_rate

    except optuna.TrialPruned:
        raise
    except Exception as e:
        print(f"[Trial {trial.number}] Failed with error: {e}")
        return 0.0

if __name__ == "__main__":
    print("=== STARTING VIX HYPERPARAMETER OPTIMIZATION ===" )
    
    # Create an Optuna study aimed at maximizing the win rate
    study = optuna.create_study(direction="maximize")
    
    # Run optimization for a designated number of trials (e.g., 30 to 50 iterations)
    study.optimize(objective, n_trials=30)

    print("\n==============================================")
    print("         OPTIMIZATION COMPLETE                ")
    print("===============================================")
    print(f"Best Win Rate Achieved: {study.best_value:.2f}%")
    print("Optimal VIX Parameters Found:")
    for key, value in study.best_params.items():
        print(f"  {key}: {value:.4f}")
    print("===============================================")
