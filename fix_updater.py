import pathlib

content = pathlib.Path('chzzktube/infra/updater.py').read_text(encoding='utf-8')

# _frozen_upgrade_streamlink 함수 전체 제거
start = content.find('def _frozen_upgrade_streamlink():')
if start >= 0:
    next_def = content.find('\ndef ', start + 1)
    if next_def < 0:
        next_def = len(content)
    content = content[:start] + content[next_def:]

# upgrade_packages 함수가 _refresh_overlay_sys_path 함수 이후에 올바르게 위치하도록 추가
insert_pos = content.find('def _refresh_overlay_sys_path():')
if insert_pos >= 0:
    next_def = content.find('\ndef ', insert_pos + 1)
    if next_def < 0:
        next_def = len(content)
    upgrade_func = '''

def upgrade_packages(packages, channel="stable"):
    """직접 다운로드 방식으로 패키지 업데이트 (Dev/Frozen 통합).

    [v3.4.0 변경] 해제 대상은 프로젝트 오버레이(.pylib/) -- venv(site-packages,
    uv 소유)는 절대 건드리지 않는다. 요약 문자열에 "(overlay)" 표기.
    이유: 포터블 빌드와 Dev에서 동일한 코드 경로를 타야 디버깅이 가능.
    pip install은 빌드 시에만 사용 (PyInstaller 번들 시점).

    Returns (returncode, output tail). Worker thread only.
    """
    # yt-dlp: Dev/Frozen 통합 - 직접 다운로드 (yt_dlp_binary 위임)
    if "yt-dlp" in packages:
        return _frozen_upgrade_ytdlp(channel)
'''
    content = content[:next_def] + upgrade_func + content[next_def:]

pathlib.Path('chzzktube/infra/updater.py').write_text(content, encoding='utf-8')
print('Done')