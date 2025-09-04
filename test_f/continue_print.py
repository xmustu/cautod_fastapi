#!/usr/bin/env python3
import time
import os
os.environ["PYTHONUNBUFFERED"] = "1"
for sec in range(1, 11):
    print(f"[{sec:02d}/60] Hello, this is message #{sec}", flush=True)
    time.sleep(1)

print("Done! 60 seconds are up.", flush=True)