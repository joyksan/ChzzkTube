import sys
sys.path.insert(0, r"c:\dev\ChzzkTube")
import media
from log_console import format_analysis_counts
from media import cli_format_desc, audio_spec, short_codec, codec_detail

# 친직 클립 AnalyzeWorker v_list 구축 로직 정확 재현 (downloader.py 180-215 + chzzk_api 포맷)
def chzzk_clip_vlist(ch_info):
    v_list = []
    for fmt in ch_info.get("formats", []):
        v_list.append({
            "id": fmt["id"],
            "height": fmt["height"],
            "fps": fmt.get("fps", 0),
            "vcodec": fmt.get("vcodec", ""),
            "acodec": fmt.get("acodec", ""),
            "bitrate": fmt["bitrate"],
            "tbr": fmt["bitrate"],
            "label": cli_format_desc({
                "ext": "mp4", "height": fmt.get("height"),
                "fps": fmt.get("fps") or None, "tbr": fmt.get("bitrate"),
                "protocol": "https", "vcodec": fmt.get("vcodec"),
                "acodec": fmt.get("acodec"),
            }),
        })
    return v_list

# chzzk clip 샘플 (2개 progressive, acodec='AAC')
clip = {"formats": [
    {"id":"url_720","height":720,"fps":60,"vcodec":"H.264","acodec":"AAC","bitrate":695,"url":"url_720"},
    {"id":"url_360","height":360,"fps":30,"vcodec":"H.264","acodec":"AAC","bitrate":300,"url":"url_360"},
]}
v_list = chzzk_clip_vlist(clip)
a_list = []
all_integrated = bool(v_list) and all(str(v.get("acodec","none")) not in ("none","") for v in v_list)
print("counts:", format_analysis_counts(len(v_list), len(a_list)))
print("_all_integrated:", all_integrated)
print("cb_video items:")
print("  [auto]")
for v in v_list:
    print("  -", repr(v["label"]), "id=", v["id"], "acodec=", repr(v["acodec"]), "vcodec=", repr(v["vcodec"]))
# integrated audio combo 재현
groups={}; order=[]
for v in v_list:
    ac=str(v.get("acodec","none"))
    if ac in ("none",""): continue
    spec=audio_spec(ac)
    if spec not in groups: groups[spec]=[]; order.append(spec)
    groups[spec].append(v["id"])
print("cb_audio items (integrated):")
for spec in order:
    print("  -", spec, "ids=", groups[spec])
sel = v_list[0]
print("selected video header line ->", "비디오:", cli_format_desc({"ext":"mp4","height":sel.get("height"),"fps":sel.get("fps") or None,"tbr":sel.get("bitrate"),"protocol":"https","vcodec":sel.get("vcodec"),"acodec":sel.get("acodec")}))





