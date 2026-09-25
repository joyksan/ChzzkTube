# Chzzktube v3.11.0 리팩토링 작업 목록

## Phase 1: yt-dlp 독립 실행형 바이너리 마이그레이션 (최우선) ✅ 완료

### Task 1.1: provisioning/resolver.py에서 yt-dlp PYTHON_PKG 스펙 제거
- [x] `MIRROR_REGISTRY`에 yt-dlp 엔트리가 없는지 확인 (이미 제거됨)
- [x] `ComponentType.PYTHON_PKG`가 yt-dlp용으로만 쓰였는지 확인 후 미사용 시 제거 검토 (테스트용으로만 사용 중, 유지)

### Task 1.2: updater.py - installed_version()에서 yt-dlp .pylib 스캔 완전 제거
- [x] yt-dlp 분기에서 이미 `yt_dlp_binary.yt_dlp_version()` 사용 중 — 확인만
- [x] 주석에서 `.pylib` 스캔 언급 제거 (SSOT 주석 정리: "바이너리 전용" 추가)

### Task 1.3: updater.py - upgrade_packages()에서 yt-dlp whl 경로 제거 확인
- [x] 이미 `_frozen_upgrade_ytdlp()` → `yt_dlp_binary.upgrade_yt_dlp()` 위임 중 — 확인만
- [x] docstring에 `.pylib 미사용` 명시

### Task 1.4: yt_dlp_binary.py - Nightly 채널 다운로드 URL 검증 및 보강
- [x] `_YTDLP_NIGHTLY_API` URL을 `_YTDLP_NIGHTLY_BASE`로 변경 (GitHub nightly-builds)
- [x] nightly 바이너리 이름 규칙: `_platform_asset_name()` 재사용으로 플랫폼별 처리 (macOS `_macos` 접미사 등)
- [x] `ensure_yt_dlp()` / `upgrade_yt_dlp()` nightly 채널 정상 작동 확인

### Task 1.5: yt_dlp_binary.py - Silent Fallback 제거 (FAIL FAST)
- [x] `_latest_stable_version()`의 `except Exception: pass` → `log_f12_net()`로 명시적 에러 로깅 + 폴백 반환
- [x] `_download_with_progress()` 에러 처리 검증 (이미 `log_f12_net` 사용 중)
- [x] `ensure_yt_dlp()` 예외 처리 → 명시적 에러 이벤트 반환 (이미 구현됨)

### Task 1.6: 테스트 작성 및 검증
- [x] 기존 테스트 스위트 통과 확인 (`pytest -m "not integration" -q` → 360 passed)
- [ ] `test_yt_dlp_binary.py` 생성: 버전 감지, 다운로드, 업그레이드 테스트 (선택적)

---

## Phase 2: Silent Fallback 완전 제거 (최우선) ✅ 완료

### Task 2.1: 전체 bare 예외 핸들러 감사 및 인벤토리 작성
- [x] `grep -r "except Exception: pass" --include="*.py" chzzktube/` → 0개 (모두 수정됨)
- [x] `grep -r "except:" --include="*.py" chzzktube/` (bare except) → 0개 (모두 수정됨)
- [x] 각 항목 분류: FAIL FAST vs LOG + FAIL

### Task 2.2: 고우선순위 수정 ✅ 완료
- [x] `po_client.py`: PID 검증 `except Exception:` → 명시적 F12 에러 로깅
- [x] `live_recorder.py`: bare `except:` → 타입별 예외 + 에러 이벤트 (2곳 수정)
- [x] `pot_server.py`: 모든 `except Exception:` 패턴 → F12 에러 로깅 추가 (15+곳)
- [x] `provisioning/manager.py`: `_refresh_path()`, `_fetch_latest()`, `_fetch_nodejs_sha256()`, `_ensure_nodejs_npm_links()` → 에러 로깅
- [x] `provisioning/resolver.py`: `filter_assets()` 중복 sort 제거, `get_platform_asset_filters()` 로깅 추가
- [x] `node_provider.py`: `node_major_version()` 이미 에러 로깅 있음 (LOG + FAIL 패턴)
- [x] `provisioning/manifest.py`: `load()` 에러 로깅 추가
- [x] `updater.py`: 주요 `except Exception:` 패턴들 F12 로깅 추가

### Task 2.3: FAIL FAST 계약 구현
- [x] 프로비저닝 함수들: 에러 시 명시적 로깅 + 기본값 반환 (LOG + FAIL 패턴)
- [x] `ensure_node_server()`: `(result, error)` 튜플로 명시적 에러 반환
- [x] TUI/F12 로그에 명시적 실패 사유 표시 (F12 로깅 추가됨)

---

## Phase 3: 진행률 바 재구성 + TUI/F12 채널 격리 (높음) ✅ 완료

### Task 3.1: 진행률 바 메시지 포맷 변경 (TUI용 최소 영문, 55자 이내)
- [x] `progress_bar.py` MSG: `downloading` | `completed` | `failed` | `verifying` (또는 "starting")
- [x] MB/ETA/speed 제거, 구조화 필드(`pct`, `speed`, `bar_frac`)로 분리

### Task 3.2: 필드 순서 재구성 (PCT → SPEED → BAR → MSG)
- [x] `log_emitter.py` `emit_progress()` 순서 있는 필드 수용 (이미 pct, speed, bar_frac, msg 분리)
- [x] `ProgressBar._emit()` 순서 있는 메시지 구성
- [x] `log_console.py` 필드 순서 준수 렌더링 (기존 format_log_line이 PCT→SPEED→BAR→MSG 순서)

### Task 3.3: TUI/F12 채널 격리 구현
- [x] TUI (`to_tui=True`): 제자리 갱신(`is_status=True` + `component_id` + `is_progress=True`) - 기존 구현 사용
- [x] F12/파일 (`to_tui=False`): CLI 원문, HTTP 헤더, 검증 상세, 트레이스백 전량 보존 - 기존 log_f12_cli, log_f12_net 사용
- [x] 뷰 계층: `component_id` 진행 틱 → 동일 라인 덮어쓰기, 완료 시 `status="OK"` 커밋 - log_console.py의 _update_progress_line / reflow 구현

---

## Phase 4: 의존성 프로비저닝 심층 리뷰 (최우선) - Phase 3 완료 후

### Task 4.1: ProvisioningManager 3개 클래스 분리 (Planner/Executor/Committer) ✅ 완료
- [x] `Planner`: `resolve()` → plans (planner.py)
- [x] `Executor`: `provision(plans)` → results (executor.py)
- [x] `Committer`: `commit(plans, results)` → manifest + overlay (committer.py)
- [x] ProvisioningManager가 파사드 패턴으로 위임 구조로 리팩토링

### Task 4.2: Pot Server 로직 단계별 분리 ✅ 완료
- [x] `ensure_node_server()` 200줄+ → 단계별 분리 (helper 함수들)
- [x] `npm ci` / `tsc` 타임아웃 → 명시적 `ProvisionResult` 에러
- [x] `acquire_prewarm_lock()` `int | None` → `Result` 표준화

### Task 4.3: 재프로비저닝 가드 (멱등성, 진행률 바 조건부 표시) ✅ 완료
- [x] `ensure_all(stale_only=True)` 이미 최신 컴포넌트 스킵 검증 (planner의 stale_only 체크)
- [x] 멱등성 체크: 버전 X 이미 있으면 재다운로드 안 함 (manifest의 is_stale 체크)
- [x] 진행률 바: 실제 다운로드/설치만 표시, "이미 최신"엔 미표시 (planner가 non-stale 제외)

### Task 4.4: Bridge 동기/비동기 경계 검증 ✅ 완료
- [x] `bridge.py`: `asyncio.run()` sync 컨텍스트 → 중첩 이벤트 루프 확인
- [x] `update_worker.py`: `_do_upgrade()` 매 실행 `ProvisioningManager` 재생성 → 재사용 검토

---

## 체크포인트
- [x] Phase 1 완료 후 전체 테스트 실행 (`pytest -m "not integration" -q`) → 360 passed
- [x] Phase 2 완료 후 전체 테스트 실행 → 360 passed
- [x] Phase 3 완료 후 전체 테스트 실행 → 360 passed
- [x] Phase 4 완료 후 전체 테스트 실행 → 361 passed
- [ ] 코드 리뷰 5축 품질 게이트 통과