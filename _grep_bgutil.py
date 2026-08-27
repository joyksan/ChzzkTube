# _grep_bgutil.py
import os, yt_dlp

root = os.path.join(os.path.dirname(yt_dlp.__file__), "extractor")
out = []
for dp, _, fns in os.walk(root):
    for fn in fns:
        if not fn.endswith(".py"):
            continue
        fp = os.path.join(dp, fn)
        try:
            txt = open(fp, encoding="utf-8", errors="replace").read()
        except Exception:
            continue
        if "bgutil" in txt:
            out.append(fp)
open(r"c:\dev\ChzzkTube\_bgutil_files.txt", "w", encoding="utf-8").write("\n".join(out) or "(none)")
print(len(out))