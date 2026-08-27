import subprocess, sys, os
os.chdir(r"c:\dev\ChzzkTube")
p = subprocess.Popen(
    [sys.executable, "main.py"],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
)
try:
        out, _ = p.communicate(timeout=2)
    tag = "CLEAN rc=%d" % p.returncode
except subprocess.TimeoutExpired:
    p.kill()
    out, _ = p.communicate()
    tag = "KILLED_4s"
with open("_run_out.txt", "wb") as f:
    f.write(out)
print("TAG=%s LEN=%d" % (tag, len(out)), flush=True)
