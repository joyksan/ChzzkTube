##### downloader_helpers/client_opts.py - yt-dlp 옵션 빌더
"""yt-dlp 옵션에 player_client/쿠키 설정을 주입하는 순수 헬퍼."""
import os
import shutil


def _apply_ffmpeg_opts(opts):
    """ffmpeg 경로를 ydl_opts에 반영 (Windows/macOS/Linux 호환)."""
    # 이미 ffmpeg_location이 설정되어 있으면 스킵
    if "ffmpeg_location" in opts:
        return opts
    # 시스템 PATH에서 ffmpeg 검색 (Windows에서는 ffmpeg.exe도 시도)
    ffmpeg_path = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
    if ffmpeg_path:
        opts["ffmpeg_location"] = ffmpeg_path
    return opts


def _apply_client_opts(opts, cfg, forced=None):
    """유튜브 player_client 수동 지정을 ydl_opts에 반영 (성인제한 대응).

    forced가 주어지면(분석 단계에서 실증·통과한 클라이언트) cfg 값보다
    우선한다. 다운로드가 분석과 같은 클라이언트를 쓰도록 해 PO 토큰/
    봇 게이트 경로 재진입(0% 스톨)을 막는다.
    """
    client = str(forced or cfg.get("yt_player_client", "auto") or "auto")
    if client != "auto":
        opts["extractor_args"] = {"youtube": {"player_client": [client]}}
    return opts


def _apply_cookie_opts(opts, cfg):
    """브라우저 쿠키 설정을 ydl_opts에 반영 (4곳 중복 제거 공통 헬퍼)."""
    browser = cfg.get("browser_cookie", "none")
    if browser not in ["none", "auto", "cookie_file"]:
        opts["cookiesfrombrowser"] = (browser,)
    elif browser == "cookie_file" and os.path.exists(cfg.get("cookie_file_path", "")):
        opts["cookiefile"] = cfg["cookie_file_path"]
    return opts


def _apply_ejs_opts(opts):
    """YouTube JS 챌린지(n-sig) 솔버 원격 수급 — ejs:github 허용.

    [배경] YouTube가 web 계열 클라이언트에 JS 챌린지를 요구할 때
    기본 설정은 원격 솔버 다운로드를 skip해 'page needs to be reloaded'
    오류로 귀결된다. ejs:github 허용치를 주면 GitHub에서 챌린지 솔버
    스크립트를 자동 수급해 n-sig 해결을 돕는다.
    """
    if "remote_components" not in opts:
        opts["remote_components"] = []
    if "ejs:github" not in opts["remote_components"]:
        opts["remote_components"].append("ejs:github")
    return opts


def _apply_light_analysis_opts(opts):
    """[경량 분석] YouTube HLS/DASH 매니페스트 열거 생략 — 분석 스톨 차단.

    yt-dlp youtube 추출기는 web 붕괴 시 tv/visionos 등 HLS 계열 클라이언트로
    폴백하며, 이때 'Downloading m3u8 information' 단계에서 매니페스트 전체
    변형을 내려받는다. 이 요청은 googlevideo 셔드 지연/스로틀 환경에서
    멈춰 분석이 'analyzing...'에 영원히 갇히는 원인이 된다.

    분석은 채널명/제목/포맷 개수 등 기본 정보만 필요하므로 매니페스트를
    열거하지 않고 플레이어 응답의 직접 URL 포맷만 취한다. 실제 데이터 수급
    (매니페스트 재열거 + JS 챌린지/PO 토큰 우회)은 DownloadWorker의 무거운
    경로가 담당한다 — 가벼운 동작(살펴보기)과 무거운 동작(내려받기) 분리.
    """
    ea = opts.setdefault("extractor_args", {}).setdefault("youtube", {})
    skip = ea.setdefault("skip", [])
    for manifest in ("hls", "dash"):
        if manifest not in skip:
            skip.append(manifest)
    return opts


def _apply_pot_opts(opts, video_id, client="web_embedded"):
    """bgutil 독립 서버에서 PO 토큰을 직접 패칭해 extractor_args로 주입.

    [변경] 기존 Python 플러그인(yt_dlp_plugins/getpot_bgutil) 자동 주입을
    제거하고, 앱이 bgutil HTTP 서버에 POST /get_pot를 직접 호출해
    `youtube:po_token=CLIENT.gvs+TOKEN` 형태로 명시 전달한다.
    - 플러그인 제거 → 토큰 생성이 블랙박스가 아니라 앱이 완전히 제어
    - 서버 미기동/오류 시 None → PO 없이 진행 (플러그인 실패와 달리 조용)
    - player_client가 이미 설정돼 있으면 병합 (덮어쓰지 않음)
    """
    if not video_id:
        return opts
    import pot_provider
    token = pot_provider.fetch_po_token(video_id)
    if not token:
        return opts
    ea = opts.setdefault("extractor_args", {}).setdefault("youtube", {})
    # po_token은 list[str] — 기존 값 유지하며 gvs 컨텍스트만 추가
    ea.setdefault("po_token", []).append(f"{client}.gvs+{token}")
    return opts


def _dedupe_by_label(formats):
    """표시 라벨이 동일한 포맷은 대표 1개만 남긴다 (라이브 HLS 중복 제거)."""
    seen, unique = set(), []
    for fmt in formats:
        if fmt["label"] not in seen:
            seen.add(fmt["label"])
            unique.append(fmt)
    return unique
