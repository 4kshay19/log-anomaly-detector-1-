"""Simulate a growing app log with periodic error bursts of increasing severity."""
import argparse
import random
import time

p = argparse.ArgumentParser()
p.add_argument("--file", default="logs/app.log")
p.add_argument("--rate", type=float, default=20, help="lines per second")
p.add_argument("--normal-error", type=float, default=0.03)
p.add_argument("--first-burst", type=float, default=75, help="seconds until first burst")
p.add_argument("--burst-every", type=float, default=120)
p.add_argument("--burst-duration", type=float, default=40)
args = p.parse_args()

BURST_RATES = [0.12, 0.20, 0.50]   # roughly MEDIUM, HIGH, CRITICAL
SERVICES = ["auth", "payments", "orders", "search", "gateway"]
OK = ["request completed", "cache hit", "user login", "order created"]
ERR = ["db connection timeout", "upstream 502", "payment declined: gateway error", "null pointer"]

start = time.time()
print(f"Writing to {args.file} at {args.rate:g} lines/s (Ctrl+C to stop)")
with open(args.file, "a", buffering=1) as f:
    while True:
        t = time.time() - start
        err = args.normal_error
        if t >= args.first_burst:
            k, off = divmod(t - args.first_burst, args.burst_every)
            if off < args.burst_duration:
                err = BURST_RATES[int(k) % len(BURST_RATES)]
        is_err = random.random() < err
        level = "ERROR" if is_err else random.choices(["INFO", "WARN", "DEBUG"], [90, 7, 3])[0]
        msg = random.choice(ERR if is_err else OK)
        f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {level} {random.choice(SERVICES)} {msg}\n")
        time.sleep(1 / args.rate)
