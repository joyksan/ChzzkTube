import importlib.util, shutil, sys
print("py:", sys.version.split()[0])
print("bgutil_spec:", importlib.util.find_spec("bgutil_ytdlp_pot_provider"))
print("node:", shutil.which("node"))
print("streamlink:", shutil.which("streamlink"))
print("ffmpeg:", shutil.which("ffmpeg"))
