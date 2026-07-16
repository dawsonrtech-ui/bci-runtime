import numpy as np
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.cect import CECT

print("=== CECT Test ===")

cect = CECT(n_commands=8, d_model=32, n_heads=2, n_layers=2, d_ff=64, max_seq=16)

commands = np.array([0, 1, 2, 3, 4, 5, 3, 2], dtype=np.int64)
confidences = np.array([0.9, 0.85, 0.7, 0.6, 0.8, 0.75, 0.65, 0.55], dtype=np.float64)

print("\nPre-training:")
corrected, conf = cect.correct(commands, confidences)
print(f"  Raw last command: {commands[-1]}")
print(f"  Corrected: {corrected} (confidence: {conf:.3f})")

print("\nTraining on synthetic data...")
losses = cect.train_on_synthetic(n_epochs=20, sequences_per_epoch=500, lr=0.01)
print(f"  Initial loss: {losses[0]:.4f}")
print(f"  Final loss:   {losses[-1]:.4f}")

print("\nPost-training:")
corrected, conf = cect.correct(commands, confidences)
print(f"  Raw last command: {commands[-1]}")
print(f"  Corrected: {corrected} (confidence: {conf:.3f})")

print("\nInference timing:")
import time
n_runs = 1000
t0 = time.perf_counter()
for _ in range(n_runs):
    cect.correct(commands, confidences)
avg_us = (time.perf_counter() - t0) / n_runs * 1e6
print(f"  Average inference: {avg_us:.1f} us ({avg_us/1000:.2f} ms)")

print("\n=== CECT Test Complete ===")
