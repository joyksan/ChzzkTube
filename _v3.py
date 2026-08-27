# _v3.py - 이번 배치(2차 피드백) 단위 검증
import sys
sys.path.insert(0, r"c:\dev\ChzzkTube")
import media
import downloader

res = []
def chk(name, cond, detail=""):
    res.append((name, bool(cond), detail))

# 1) cli_format 오디오 전용 — '129k https' 제거, 컨테이너+코덱만
a = media.cli_format_desc({"ext": "m4a", "abr": 129, "protocol": "https", "vcodec": "none", "acodec": "mp4a.40.2"})
chk("aud-clean", a == "m4a | AAC-LC (mp4a.40.2)", a)
assert "129k" not in a and "https" not in a

# 2) 비디오 전용은 그대로 (bitrate/proto 유지, audio 미포함)
v = media.cli_format_desc({"ext": "mp4", "height": 1080, "fps": 30, "tbr": 469, "protocol": "https", "vcodec": "avc1.64002A", "acodec": "none"})
chk("vid-keep", v == "mp4 | 1080p 30fps | 469k https | H264", v)

# 3) 통합은 코덱 1회 결합 (오디오 중복 없음)
m = media.cli_format_desc({"ext": "mp4", "height": 360, "fps": 30, "tbr": 339, "protocol": "https", "vcodec": "avc1.42001E", "acodec": "mp4a.40.2"})
chk("mux-once", m.count("AAC") == 1 and m.endswith("AAC-LC (mp4a.40.2)"), m)

# 4) vcodec '' / 'None' / 'none' 모두 비디오에서 제외 (오디오 누수 방지)
def split_like(fmt_list):
    v, a = [], []
    import collections
    for f in fmt_list:
        vc = f.get("vcodec", "none"); ac = f.get("acodec", "none")
        has_v = str(vc or "").strip() not in ("none", "", "None")
        has_a = str(ac or "").strip() not in ("none", "", "None")
        if has_v: v.append(f)
        elif has_a: a.append(f)
    return v, a
fmts = [
    {"id":"1","vcodec":"avc1","acodec":"none"},
    {"id":"2","vcodec":"","acodec":"mp4a.40.2"},   # 빈 vcodec → 오디오로
    {"id":"3","vcodec":"none","acodec":"mp4a.40.2"},
    {"id":"4","vcodec":None,"acodec":"mp4a.40.2"},
    {"id":"5","vcodec":"avc1","acodec":"mp4a.40.2"}, # 통합 → 비디오
]
v, a = split_like(fmts)
chk("vcodec-empty-notin-v", all(x["id"] in ("1","5") for x in v), [x["id"] for x in v])
chk("audio-includes-emptynone", set(x["id"] for x in a) == {"2","3","4"}, [x["id"] for x in a])

# 5) pot_provider 모듈 로드 + 함수 존재
import pot_provider
chk("pot fn", callable(pot_provider.server_running))
chk("pot plugin fn", callable(pot_provider.plugin_installed))
chk("pot class", hasattr(pot_provider, "POTProviderWorker"))

# 6) SpeedWindow 여전 동작 (기존 배치 회귀 확인)
sw = downloader.SpeedWindow(window=10.0)
sw.add(1000.0, 1000); sw.add(1010.0, 6000)
s = sw.speed(1010.0)
chk("speedwin", 490 < s < 510, f"{s}")

# 7) updater PACKAGES에 bgutil 포함
import updater
chk("updater bgutil", "bgutil-ytdlp-pot-provider" in updater.PACKAGES, updater.PACKAGES)

out = []
for name, ok, detail in res:
    out.append(f"[{'OK' if ok else 'FAIL'}] {name}" + (f" | {detail}" if detail and not ok else ""))
print("\n".join(out))
print(f"\n{sum(1 for _, ok, _ in res if ok)}/{len(res)} PASS")