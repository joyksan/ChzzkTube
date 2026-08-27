import subprocess, sys
p = subprocess.Popen(
    [sys.executable, "main.py"],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
)
try:
        out = p.communicate(timeout=4)[0]
    print("===CLEAN_EXIT===")
except subprocess.TimeoutExpired:
    p.kill()
    out = p.communicate()[0]
    print("===KILLED_6s===")
print("===BEGIN===")
sys.stdout.write(out.decode("utf-8", "replace"))
print("\n===END===")
