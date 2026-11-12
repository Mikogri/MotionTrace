"""Run the actual model smoke test with outbound socket operations denied.

Use the motiontrace-vision interpreter and the same arguments as ai/vision/smoke.py.
The guard affects this test process only; no firewall or system settings change.
"""
from pathlib import Path
import runpy
import socket
import sys


def denied(*args, **kwargs):
    raise RuntimeError("Network access attempted during the offline model test")


socket.socket.connect = denied
socket.socket.connect_ex = denied
socket.create_connection = denied
socket.getaddrinfo = denied
script = Path(__file__).resolve().parents[1] / "ai" / "vision" / "smoke.py"
sys.argv[0] = str(script)
runpy.run_path(str(script), run_name="__main__")
