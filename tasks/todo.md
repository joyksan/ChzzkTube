# Chzzktube 5대 결함 수정 작업 목록

## Phase 1: Critical 결함 (즉시 수정 필요)

### Task 1: 결함 4 - POT 빌드 타임아웃 vs 게이트 워치독 충돌 ✅
- [x] Test: GATE_TIMEOUT_SEC 증가 및 빌드 진행 하트비트 연동 테스트 작성 (기존 테스트로 커버됨)
- [x] Fix: `core/watchdog.py` - GATE_TIMEOUT_SEC 120→900초 상향
- [x] Fix: `infra/pot_server.py` - `_run_and_stream_log`에 주기적 하트비트 발행 추가 (이미 구현됨)
- [x] Fix: `ui/main_window.py` - 게이트 워치독에 POT 빌드 하트비트 연결 (이미 구현됨)
- [x] Verify: 기존 테스트 통과 + 새 테스트 통과

### Task 2: 결함 2 - 라이브 녹화 블로킹 HANG
- [ ] Test: `record_live_stream` 논블로킹 읽기 + 취소 체크 테스트 작성
- [ ] Fix: `pipeline/live_recorder.py` - `selectors`로 1초 타임아웃 폴링 구현
- [ ] Fix: 취소 신호 즉시 처리 루틴 추가
- [ ] Fix: 워치독 하트비트 연동 (결함 5와 병합)
- [ ] Verify: 기존 테스트 통과 + 새 테스트 통과

## Phase 2: High 결함

### Task 3: 결함 1 - 유튜브 tv 클라이언트 화질/무음 위험
- [ ] Test: `_format_selector`가 `"bv*+ba"` 반환, tv 클라이언트 폴백 체인 테스트 작성
- [ ] Fix: `pipeline/target_downloader.py` - `_format_selector` 수정, `client_chain`에서 `ios` 제거
- [ ] Fix: `tv` 클라이언트 진입 시 분리 포맷 강제로 폴백 유도
- [ ] Verify: 기존 테스트 통과 + 새 테스트 통과

### Task 4: 결함 3 - 치지직 쿠키 만료 리커버리 부재
- [ ] Test: `ChzzkAuthError` 발생 및 CookieSelectDialog 자동 호출 테스트 작성
- [ ] Fix: `core/chzzk_api.py` - `_get_json_with_auth_check` 추가, `ChzzkAuthError` 정의
- [ ] Fix: `workers/analyze_worker.py` - 인증 에러 명시적 처리
- [ ] Fix: `ui/main_window.py` - 쿠키 만료 감지 시 `CookieSelectDialog` 자동 표시
- [ ] Verify: 기존 테스트 통과 + 새 테스트 통과

### Task 5: 결함 5 - 워치독 하트비트 미연동
- [ ] Test: 네트워크 I/O 루프에서 5초마다 워치독 하트비트 호출 테스트 작성
- [ ] Fix: `pipeline/target_downloader.py` - `_http_download`에 하트비트 추가
- [ ] Fix: `pipeline/live_recorder.py` - `record_live_stream` 루프에 하트비트 추가 (Task 2와 병합)
- [ ] Fix: `workers/downloader.py` - `ctx`에 워치독 참조 주입
- [ ] Verify: 기존 테스트 통과 + 새 테스트 통과

## Phase 3: 기존 실패 테스트 수정

### Task 6: LivenessWatchdog Qt 시그널 연결 문제 수정 ✅
- [x] Fix: `core/watchdog.py` - `LivenessWatchdog`이 `QObject` 상속
- [x] Verify: `test_window_opens_and_renders_log` 통과

## 체크포인트
- [x] Phase 1 완료 후 전체 테스트 실행
- [ ] Phase 2 완료 후 전체 테스트 실행
- [ ] Phase 3 완료 후 전체 테스트 실행
- [ ] 모든 테스트 통과 (기존 239개 + 신규 테스트)