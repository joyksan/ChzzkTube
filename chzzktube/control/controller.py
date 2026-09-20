### controller.py - 다운로드 세션의 상태 머신 및 DownloadWorker 생명주기 관리
import os
import re
import urllib.parse
from dataclasses import dataclass, replace
from typing import Optional

from PySide6.QtCore import QObject, Signal, QThread

from chzzktube.core.dl_platform import _DOMAIN_EXTRACTORS
from chzzktube.workers.analyze_worker import AnalyzeWorker
from chzzktube.workers.downloader import DownloadWorker


# ── [v3.8.0] URL Validation Gate — 순수 함수 (컨트롤러/뷰 공용) ──────────────
# 알려진 도메인 추출기 테이블을 단일 진실 공급원으로 재사용
# (dl_platform._DOMAIN_EXTRACTORS: chzzk/youtube/twitch/instagram 등)
_KNOWN_DOMAINS = tuple(p for p, _ in _DOMAIN_EXTRACTORS)


def _is_valid_url(url) -> bool:
    """입력 문자열이 다운로드 가능한 URL 규격인지 사전 검증 (v3.8.0).

    `afqweqasd` 같은 임의 문자열이 DownloadWorker까지 유입되어
    [generic] Extracting URL → DL FAIL 다중 로그를 남기는 것을 원천 차단.

    규칙:
    - 스킴 필수: http:// 또는 https:// 로 시작
    - 도메인 필수: 파싱 성공 + '.' 포함 + 알려진 도메인 계열(suffix 매치)
    - 실패 예시: 'afqweqasd', 'https://afqweqasd.com'(미지원 도메인)
    - 통과 예시: 'https://youtu.be/xxx', 'https://chzzk.naver.com/...'
    """
    s = str(url or "").strip()
    if not s.startswith(("http://", "https://")):
        return False
    try:
        host = urllib.parse.urlparse(s).netloc.lower()
    except ValueError:
        return False
    if not host or "." not in host:
        return False
    return any(host == d or host.endswith("." + d) for d in _KNOWN_DOMAINS)


@dataclass(frozen=True)
class SessionState:
    """불변 세션 상태 — 스레드 간 안전한 전달을 위해 불변 객체로 관리."""
    running: bool = False
    canceled: bool = False
    skip: bool = False
    analyzing: bool = False
    picking: bool = False  # 포맷 직접 고르기 대기 (UI pick 입력 수신 중)


class MediaController(QObject):
    """다운로드 + 분석 세션의 상태 머신과 생명주기를 통치하는 완벽한 컨트롤러.

    계약:
    *  SessionState 불변 객체로 상태 관리 — 스레드 간 공유 시 replace()로 새 인스턴스 생성
    *  상태 변경은 시그널(canceled_changed, skip_changed, analyzing_changed)로만 전달
    *  워커 → UI 통보는 Qt 시그널(finished_all/result_ready/error_occurred)로만
    *  분석 워커 종료 시 quit() + wait()로 정상 종료 보장 (좀비 패턴 제거) """

    # ── 분석 워커 시그널 포워딩 (View 바인딩용) ──
    # [v3.3.0] 로그는 raw 버스 단일 경유 — analyze_log_full 포워딩 폐기.
    analyze_result_ready = Signal(dict)
    analyze_error_occurred = Signal(str)
    # [Watchdog] 분석 진행 하트비트 포워딩. 뷰가 소유한 분석 워치독 수명을 연장한다.
    analyze_activity = Signal()
    # ── 상태 변경 시그널 (UI 스레드에서만 emit, 워커는 읽기 전용) ──
    canceled_changed = Signal(bool)
    skip_changed = Signal(bool)
    analyzing_changed = Signal(bool)

    def __init__(self, view):
        super().__init__()
        self.view = view
        self._state = SessionState()
        self.worker_dl: Optional[DownloadWorker] = None
        self.worker_analyze: Optional[AnalyzeWorker] = None

    # ── 상태 읽기 전용 프로퍼티 ──
    @property
    def state(self) -> SessionState:
        return self._state

    @property
    def running(self) -> bool:
        return self._state.running

    @property
    def analyzing(self) -> bool:
        return self._state.analyzing

    @property
    def picking(self) -> bool:
        return self._state.picking

    # ── 상태 변경 메서드 (불변 객체 교체 + 시그널 emit) ──
    def _set_running(self, val: bool):
        if self._state.running != val:
            self._state = replace(self._state, running=val)

    def _set_canceled(self, val: bool):
        if self._state.canceled != val:
            self._state = replace(self._state, canceled=val)
            self.canceled_changed.emit(val)

    def _set_skip(self, val: bool):
        if self._state.skip != val:
            self._state = replace(self._state, skip=val)
            self.skip_changed.emit(val)

    def _set_analyzing(self, val: bool):
        if self._state.analyzing != val:
            self._state = replace(self._state, analyzing=val)
            self.analyzing_changed.emit(val)

    def _set_picking(self, val: bool):
        if self._state.picking != val:
            self._state = replace(self._state, picking=val)

    # ── 분석 워커 생명주기 ──
    def spawn_analyzer(self, url, cfg, deep=False):
        """URL 분석 워커 생성 및 관리 (기존 분석 정상 종료 후 교체)."""
        self._terminate_analyzer()

        self._set_analyzing(True)
        self.worker_analyze = AnalyzeWorker(url, cfg, deep=deep)
        # View 시그널로 포워딩 (Controller가 중개)
        self.worker_analyze.result_ready.connect(self.analyze_result_ready)
        self.worker_analyze.error_occurred.connect(self.analyze_error_occurred)
        self.worker_analyze.activity.connect(self.analyze_activity)
        self.worker_analyze.finished.connect(self._on_analyzer_finished)
        self.worker_analyze.start()

    def _terminate_analyzer(self):
        """분석 워커 정상 종료 (quit + wait). QThread 및 mock 모두 대응."""
        w = self.worker_analyze
        if not w:
            return
        if w.isRunning():
            # 시그널 연결 해제
            for sig in (w.result_ready, w.error_occurred, w.activity, w.finished):
                try:
                    sig.disconnect()
                except TypeError:
                    pass
            # 이벤트 루프 종료 요청 후 대기 (QThread 및 mock 대응)
            quit_method = getattr(w, "quit", None)
            if callable(quit_method):
                quit_method()
            wait_method = getattr(w, "wait", None)
            if callable(wait_method):
                if not wait_method(2000):  # 2초 대기
                    terminate_method = getattr(w, "terminate", None)
                    if callable(terminate_method):
                        terminate_method()
                    wait_method(500)
        self.worker_analyze = None
        self._set_analyzing(False)

    def abandon_analysis(self):
        """분석 중단 — 워커 정상 종료."""
        self._terminate_analyzer()

    def _on_analyzer_finished(self):
        """워커 정상 종료 시 호출."""
        self.worker_analyze = None
        self._set_analyzing(False)

    ### ── 순수 로직: 타겟 파싱 ──────────────────────────────────
    @staticmethod
    def parse_targets(raw_text, dedup=False):
        """URL/TXT 입력을 다운로드 타겟 목록으로 파싱.
        *  TXT 파일 경로면 줄 단위로 읽는다 (# 주석 제외). 실패 시 ValueError.
        *  www. 로 시작하는 항목은 https:// 접두사를 보정한다.
        *  watch?v= 단일 영상 주소 뒤 &list= / &index= / &start_radio= 플레이리스트 파라미터를 강제 제거한다.
        *  [v3.8.0] URL 규격 검증 게이트 — 비URL 임의 문자열은 즉시 ValueError.
        *  dedup=True 이면 중복 타겟을 제거한다. """
        targets = []
        if os.path.isfile(raw_text) and raw_text.lower().endswith(".txt"):
            try:
                with open(raw_text, "r", encoding="utf-8") as f:
                    for l in f:
                        t = l.strip()
                        if t and not t.startswith("#"):
                            targets.append(
                                "https://" + t if t.startswith("www.") else t
                            )
            except Exception as e:
                raise ValueError(f"TXT read fail: {e}") from e
        else:
            for l in raw_text.splitlines():
                t = l.strip()
                if t:
                    targets.append("https://" + t if t.startswith("www.") else t)

        # [v3.8.0 게이트] 검증 실패 항목 전수 수집 — 한 줄이라도 비URL이면
        # 전체 배치를 시작하지 않는다 (무검증 억지 다운로드 차단).
        invalid = [t for t in targets if not _is_valid_url(t)]
        if invalid:
            bad = invalid[0][:40] + ("..." if len(invalid[0]) > 40 else "")
            raise ValueError(f"Invalid URL format: {bad}")

        # [핵심] watch?v= 단일 영상 뒤에 붙은 플레이리스트 파라미터 강제 제거!
        cleaned_targets = []
        for u in targets:
            if "watch?v=" in u and "&list=" in u:
                u = re.sub(r"&list=[^&]+", "", u)
                u = re.sub(r"&index=[^&]+", "", u)
                u = re.sub(r"&start_radio=[^&]+", "", u)
            cleaned_targets.append(u)
        targets = cleaned_targets

        if dedup:
            targets = list(dict.fromkeys(targets))
        return targets

    ### ── 세션 상태 머신 ────────────────────────────────────────
    def begin_download(self):
        self.state.update(
            {"running": True, "canceled": False, "skip": False}
        )

    def end_download(self):
        self.state.update(
            {"running": False, "canceled": False, "skip": False}
        )

    def on_download_finished(self, success_count, fail_count):
        """다운로드 완료 후 상태 정리 (View → Controller 이관).

        View는 이 메서드를 호출만 하고, 실제 상태 초기화와 후처리는
        Controller가 담당한다. 사운드 재생/폴더 열기는 UI 전용 로직이므로
        View에서 유지한다.
        """
        self.end_download()

        if success_count > 0:
            # 분석 데이터 초기화 — 다음 URL 입력 시 깨끗한 상태로 시작
            self.view.extracted_data = {"info": None, "v_list": [], "a_list": []}

    def request_cancel(self):
        if self.running:
            self.state["canceled"] = True
        elif self.analyzing:
            self._abandon_analyzer()

    def request_skip(self):
        if self.running:
            self.state["skip"] = True

    ### ── 다운로드 워커 생명주기 ─────────────────────────────────
    def spawn_worker(
        self,
        targets,
        cfg,
        video_id,
        audio_id,
        is_live_hint=False,
        v_spec=None,
        audio_desc="",
        yt_client="auto",
    ):
        """DownloadWorker 생성 + 시그널 연결 + 구동.

        yt_client: 분석 단계에서 실증·통과한 YouTube player_client.
        다운로드가 분석과 같은 클라이언트를 쓰도록 강제 (0% 스톨 방지).
        """
        v = self.view
        w = DownloadWorker(
            targets,
            cfg,
            state_dict=None,  # 새 신호 기반 상태 사용
            v_sel=video_id,
            a_sel=audio_id,
            is_live_hint=is_live_hint,
            v_spec=v_spec,
            audio_desc=audio_desc,
            yt_client=yt_client,
            canceled_signal=self.canceled_changed,
            skip_signal=self.skip_changed,
        )
        w.finished_all.connect(v.on_download_finished)
        self.worker_dl = w
        w.start()

    def begin_download(self):
        self._set_running(True)
        self._set_canceled(False)
        self._set_skip(False)

    def end_download(self):
        self._set_running(False)
        self._set_canceled(False)
        self._set_skip(False)

    def on_download_finished(self, success_count, fail_count):
        """다운로드 완료 후 상태 정리 (View → Controller 이관)."""
        self.end_download()

        if success_count > 0:
            # 분석 데이터 초기화 — 다음 URL 입력 시 깨끗한 상태로 시작
            self.view.extracted_data = {"info": None, "v_list": [], "a_list": []}

    def request_cancel(self):
        if self.running:
            self._set_canceled(True)
        elif self.analyzing:
            self._terminate_analyzer()

    def request_skip(self):
        if self.running:
            self._set_skip(True)

    def shutdown(self, wait_ms=1000):
        """앱 종료 시 활성 스레드 안전 중단 (closeEvent용)."""
        if self.worker_dl and self.worker_dl.isRunning():
            self._set_canceled(True)
            self.worker_dl.wait(wait_ms)

        # POT 서버 워커 정리는 POTManager.cancel()이 담당 (MainWindow.closeEvent에서 호출)


# ── 하위 호환성 유지 (기존 코드에서 DownloadController로 참조 가능) ──
DownloadController = MediaController
