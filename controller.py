### controller.py - 다운로드 세션의 상태 머신 및 DownloadWorker 생명주기 관리
import os
import re

from PySide6.QtCore import QObject, Signal

from analyze_worker import AnalyzeWorker
from downloader import DownloadWorker


class MediaController(QObject):
    """다운로드 + 분석 세션의 상태 머신과 생명주기를 통치하는 완벽한 컨트롤러.

    계약:
    *  state 딕셔너리는 DownloadWorker에 참조 그대로 전달된다. 즉, 워커 스레드와 UI 스레드가 동일 객체를 공유하며 기존 MainWindow.dl_state와 완전히 동치이다.
    *  스레드 경계 — state 플래그는 단방향 쓰기: canceled/skip 는
       UI 스레드만 쓰고 워커 스레드는 읽기만 한다. CPython GIL 하에서 dict 단일 키 읽기/쓰기는 원자적이고
       각 키의 쓰기 주체가 하나뿐이므로 lock 없이도 경쟁상태(lost update)가 발생하지 않는다.
    *  워커 → UI 통보는 절대 state가 아니라 Qt 시그널(log_concise/log_full/
       finished_all/result_ready/error_occurred)로만 — 시그널 emit은 스레드 안전(QueuedConnection으로
       수신 스레드 큐에 적재)이므로 UI 위젯은 워커에서 직접 조작 금지.
    *  UI 조작(버튼/로그/진행바)은 view(MainWindow)의 메서드를 통해서만 수행한다.
    *  좀비 워커(분석 중 새 분석 요청으로 폐기된 워커)는 View가 아닌 Controller가 소유하며,
       자연 종료 시 _reap_zombie()로 메모리에서 소거한다. """

    # ── 분석 워커 시그널 포워딩 (View 바인딩용) ──
    analyze_result_ready = Signal(dict)
    analyze_error_occurred = Signal(str)
    analyze_log_full = Signal(str)

    def __init__(self, view):
        super().__init__()
        self.view = view
        self.state = {
            "running": False,
            "canceled": False,
            "skip": False,
            "analyzing": False,
            "picking": False,  # 포맷 직접 고르기 대기 (UI pick 입력 수신 중)
        }
        self.worker_dl = None
        self.worker_analyze = None
        self._zombie_workers = []  # View가 아닌 Controller가 무덤을 관리한다

    @property
    def running(self):
        return self.state["running"]

    @property
    def analyzing(self):
        return self.state["analyzing"]

    @property
    def picking(self):
        return self.state["picking"]

    # ── 분석 워커 생명주기 (main.py에서 구출 완료) ──
    def spawn_analyzer(self, url, cfg, deep=False):
        """URL 분석 워커 생성 및 관리 (기존 분석 강제 유기 포함)

        deep=True: 매니페스트(스클) 포함 포맷 목록 확보 — 포맷 직접 고르기 전용.
        """
        self._abandon_analyzer()

        self.state["analyzing"] = True
        self.worker_analyze = AnalyzeWorker(url, cfg, deep=deep)
        # View 시그널로 포워딩 (Controller가 중개)
        self.worker_analyze.result_ready.connect(self.analyze_result_ready)
        self.worker_analyze.error_occurred.connect(self.analyze_error_occurred)
        self.worker_analyze.log_full.connect(self.analyze_log_full)
        self.worker_analyze.start()

    def _abandon_analyzer(self):
        """GIL 데드락을 회피하기 위한 우아한 워커 유기 (Zombie Pattern)"""
        w = self.worker_analyze
        if not w:
            return
        if w.isRunning():
            # 시그널을 끊어 UI 오염 차단
            for sig in (w.result_ready, w.error_occurred, w.log_full):
                try:
                    sig.disconnect()
                except TypeError:
                    pass
            w.finished.connect(self._reap_zombie)
            self._zombie_workers.append(w)
        self.worker_analyze = None
        self.state["analyzing"] = False

    def _reap_zombie(self):
        """자연 종료된 유기 워커를 메모리에서 우아하게 소거한다."""
        try:
            self._zombie_workers.remove(self.sender())
        except (ValueError, AttributeError):
            pass

    ### ── 순수 로직: 타겟 파싱 ──────────────────────────────────
    @staticmethod
    def parse_targets(raw_text, dedup=False):
        """URL/TXT 입력을 다운로드 타겟 목록으로 파싱.
        *  TXT 파일 경로면 줄 단위로 읽는다 (# 주석 제외). 실패 시 ValueError.
        *  www. 로 시작하는 항목은 https:// 접두사를 보정한다.
        *  watch?v= 단일 영상 주소 뒤 &list= / &index= / &start_radio= 플레이리스트 파라미터를 강제 제거한다.
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
            self.state,
            video_id,
            audio_id,
            is_live_hint=is_live_hint,
            v_spec=v_spec,
            audio_desc=audio_desc,
            yt_client=yt_client,
        )
        w.log_concise.connect(v.append_concise_log)
        w.log_full.connect(v.append_full_log)
        w.finished_all.connect(v.on_download_finished)
        self.worker_dl = w
        w.start()

    def shutdown(self, wait_ms=1000):
        """앱 종료 시 활성 스레드 및 좀비 스레드 안전 중단 (closeEvent용)."""
        if self.worker_dl and self.worker_dl.isRunning():
            self.state["canceled"] = True
            self.worker_dl.wait(wait_ms)

        for w in list(self._zombie_workers):
            if w.isRunning():
                w.wait(1500)

        # POT 서버 워커 정리는 POTManager.cancel()이 담당 (MainWindow.closeEvent에서 호출)


# ── 하위 호환성 유지 (기존 코드에서 DownloadController로 참조 가능) ──
DownloadController = MediaController
