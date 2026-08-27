# _grep_bgutil2.py
import os, site, glob, yt_dlp

out = []
# 1) yt_dlp 패키지 전체 (extractor 외)
pkg = os.path.dirname(yt_dlp.__file__)
for dp, _, fns in os.walk(pkg):
    for fn in fns:
        if not fn.endswith(".py"):
            continue
        fp = os.path.join(dp, fn)
        try:
            txt = open(fp, encoding="utf-8", errors="replace").read()
        except Exception:
            continue
        for i, line in enumerate(txt.splitlines(), 1):
            if "bgutil" in line.lower():
                out.append(f"{fp}:{i}: {line.strip()[:160]}")

# 2) 플러그인 디렉토리
for base in (site.getusersitepackages(), *site.getsitepackages()):
    for cand in os.listdir(base):
        if "plugin" in cand.lower() and os.path.isdir(os.path.join(base, cand)):
            for dp, _, fns in os.walk(os.path.join(base, cand)):
                for fn in fns:
                    if fn.endswith(".py"):
                        fp = os.path.join(dp, fn)
                        try:
                            txt = open(fp, encoding="utf-8", errors="replace").read()
                        except Exception:
                            continue
                        if "bgutil" in txt.lower():
                            out.append(f"PLUGIN {fp}")

open(r"c:\dev\ChzzkTube\_bgutil_files2.txt", "w", encoding="utf-8").write(
    "\n".join(out) or "(none)"
)
print(len(out))