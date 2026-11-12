"""Evaluate frozen pre-change detector then restore current code even on failure."""
import subprocess,sys
from pathlib import Path
root=Path(__file__).resolve().parents[2];target=root/'src/MotionTrace.Core/Motion/MovementRepDetector.cs';current=target.read_bytes()
try:
 target.write_bytes((root/'artifacts/phase-comparison-before/MovementRepDetector.baseline.cs.txt').read_bytes())
 subprocess.run([sys.executable,str(root/'research/barbell/compare_phase_batch.py'),'artifacts/phase-engine-baseline','artifacts/phase-comparison-full-before'],cwd=root,check=True)
finally:target.write_bytes(current)
subprocess.run([sys.executable,str(root/'research/barbell/compare_phase_batch.py'),'artifacts/phase-engine-baseline','artifacts/phase-comparison-full-after'],cwd=root,check=True)
