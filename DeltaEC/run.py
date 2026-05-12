
import subprocess
import winpty
import time
import shutil
from datetime import datetime
from pathlib import Path
# Import the parser — adjust the import if you keep them in separate files.
from deltaec_parser import DeltaECFile
from plot_deltaec_phases import plot_phases

# EDIT THIS to your actual DeltaEC.exe path
DELTAEC = r"C:\Program Files\DeltaEC702\DeltaEC.exe"

base_model = "model_base.out"
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

# Build timestamped copy name: model_base_20260501_143052.out
src = Path(base_model)
backup_dir = Path("_backup")
backup_dir.mkdir(exist_ok=True)
output_model = backup_dir / src.with_stem(f"{src.stem}_{timestamp}").name

shutil.copy(base_model, output_model)

# Use base model
model_to_use = base_model
plot_to_use = model_to_use.replace(".out", ".sp")

proc = winpty.PtyProcess.spawn([DELTAEC, "-c", model_to_use])

def drain(wait=1.0):
    """Read whatever DeltaEC has printed, pause, read again."""
    time.sleep(wait)
    out = ""
    while proc.isalive():
        try:
            chunk = proc.read(4096)
            if not chunk:
                break
            out += chunk
        except EOFError:
            break
        if len(chunk) < 4096:
            break
    return out

def send(cmd):
    proc.write(cmd + "\r\n")

import re

def run_and_check():
    """Run DeltaEC and check for convergence info codes."""
    send("r")
    output = drain(2.0)
    print("=== RUN ===")
    print(output)

    # Look for "Info=" followed by a digit (case-insensitive, tolerant of spacing)
    match = re.search(r"Info\s*=\s*(\d+)", output, re.IGNORECASE)

    if match is None:
        print("[OK] Run successful — no Info code reported.")
        return True, None

    code = int(match.group(1))
    messages = {
        0: "Suspicious result (choked flow or Tm out of bounds)",
        1: "Partial convergence — residual error suspiciously large",
        2: "Max iterations reached — another run might progress further",
        3: "Tolerance too small for machine double precision",
        4: "FAILED — solver unable to converge",
    }
    msg = messages.get(code, f"Unknown info code {code}")
    print(f"[WARN] Info={code}: {msg}")
    return False, code


# Read the banner / initial prompt
print("=== BANNER ===")
print(drain(2.0))

# RUN and check for success
success, info_code = run_and_check()

# Write results
send("W")
send(model_to_use)
send("y")
print("=== WRITE RESULT ===")
print(drain(2.0))

# Exit DeltaEC
print("=== EXIT ===")
send("e")
time.sleep(1.0)
proc.close()

# Show results when successful
if (success):
    # p/U phase plotting, image file only
    plot_phases(plot_to_use, show=False)

    # output parsing
    dec = DeltaECFile(model_to_use)

    # check results

    # regenerator Edot should be positive, adding active acoustic power
    print(f"Regen d_Edot = {dec.get(27, 'F') - dec.get(26, 'F')}")
