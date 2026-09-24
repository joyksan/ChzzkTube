## 현재 상태 분석

### 1. yt-dlp 배포 방식 (최우선)
**현재**: `yt_dlp_binary.py`가 이미 GitHub 릴리스 바이너리를 `%LOCALAPPDATA%/ChzzkTube/bin/` 또는 `~/.local/bin/`에 다운로드
**문제**: `updater.py`가 여전히 `.pylib` 오버레이(whl)를 `installed_version()` / `upgrade_packages()`에 사용 — 이중 경로 불일치

### 2. Silent Fallback (최우선)
**발견된 패턴**:
- `po_client.py`: `except Exception: pass`가 PID 검증 시 NameError를 삼킴
- `live_recorder.py`: 다수의 bare `except Exception:`로 silent return
- `pot_server.py`: `except Exception:`이 로깅 없이 `None`/`False` 반환
- `provisioning/manager.py`: `_refresh_overlay()`, `_refresh_path()`에서 `except Exception: pass`
- `provisioning/resolver.py`: `filter_assets()`에 중복 `candidates.sort()`와 bare return
- `node_provider.py`: `node_major_version()`이 모든 예외에서 `None` 반환 (silent)

### 3. 진행률 바 (높음)
**현재** (`progress_bar.py`): MB/s, ETA, 다운로드/전체 MB가 MSG에 포함
**필요**: PCT → SPEED → BAR → MSG 순서, 최소한의 영문 MSG

---

## 작업 분해

### Phase 1: yt-dlp 독립 실행형 바이너리 (우선순위: 최우선) ✅ **완료**

#### Task 1.1: yt-dlp를 .pylib/whl 경로에서 제거
- [x] `updater.py`의 `PACKAGES`에서 yt-dlp 제거 확인 (이미 ytdlp만 남음)
- [x] `installed_version()`을 `bin/yt-dlp` 바이너리 확인으로 변경
- [x] `provisioning/resolver.py:44-55`에서 yt-dlp whl 미러 제거
- [x] `upgrade_packages()`를 `yt_dlp_binary.upgrade_yt_dlp()`만 호출하도록 변경

#### Task 1.2: 바이너리 버전 감지
- [x] `yt_dlp_binary.yt_dlp_version()` 기존 구현 확인 — SSOT로 확정
- [x] `updater.py`의 `check_deps()`를 `yt_dlp_binary.yt_dlp_path()` + 버전 사용으로 변경
- [x] yt-dlp에 대한 `.pylib` dist-info 스캔 완전 제거

#### Task 1.3: Dev/Frozen 경로 통합
- [x] `yt_dlp_binary._bin_dir()`이 dev/frozen 모두에서 작동하는지 확인
- [x] `_cli_base()`에서 `sys.executable -m yt_dlp` 폴백 제거

**완료 기준**: 
- [x] `yt-dlp` 바이너리가 `%LOCALAPPDATA%/ChzzkTube/bin/` 또는 `~/.local/bin/`에만 존재
- [x] `.pylib/yt_dlp-*.dist-info` 절대 생성되지 않음
- [x] `check_deps()`가 바이너리 `--version`으로 버전 리포트
- [x] `upgrade_packages()`가 GitHub 릴리스 바이너리만 다운로드

**체크포인트 1: 통과** ✅ - 모든 테스트 통과, 바이너리 경로 사용 확인됨

---

### Phase 2: Silent Fallback 완전 제거 (우선순위: 최우선)

#### Task 2.1: 모든 `except Exception: pass/return None` 패턴 감사
- [ ] 모든 bare 예외 핸들러 인벤토리 작성
- [ ] 각 항목 분류: **FAIL FAST** (에러 반환) vs **LOG + FAIL** (로그 후 에러 반환)

#### Task 2.2: 고우선순위 수정
- [ ] `po_client.py`: PID 검증 `except Exception: pass` → 명시적 에러
- [ ] `live_recorder.py`: bare `except:`를 타입별 예외 + 에러 이벤트로 변경
- [ ] `pot_server.py`: `ensure_node_server()` — `ProvisionResult.error`로 에러 전파
- [ ] `provisioning/manager.py`: `_refresh_overlay()`, `_refresh_path()` — 에러 로깅
- [ ] `provisioning/resolver.py`: `filter_assets()` — 중복 sort 제거, 명시적 반환
- [ ] `node_provider.py`: `node_major_version()` — `(major, error)` 튜플 반환 또는 예외 발생

#### Task 2.3: FAIL FAST 계약
- [ ] 모든 프로비저닝 함수가 실패 시 `ProvisionResult(success=False, error="...")` 반환
- [ ] 에러 컨텍스트 없는 silent `return None` / `return False` 금지
- [ ] TUI/F12 로그에 명시적 실패 사유 표시

**완료 기준**:
- [ ] 앱 코드에 bare `except Exception: pass` 또는 bare `except:` 제로 (테스트 제외)
- [ ] 모든 실패가 `LogEvent(is_error=True)`와 실행 가능한 메시지 생성
- [ ] `check_deps()`가 명시적 FAIL 사유 반환, silent skip 없음
---

### Phase 3: 진행률 바 재구성 (우선순위: 높음)

#### Task 3.1: 진행률 바 메시지 포맷
**현재 MSG**: `"{downloaded_mb:.1f}/{total_mb:.1f} MB {speed_str} ETA {eta_str}"`
**목표 MSG**: 최소 영문 — `"downloading" | "completed" | "failed"`

#### Task 3.2: 필드 순서 재구성
**LogEvent 필드** (`emit_progress`): `pct`, `bar_frac`, `speed`, `msg`
**TUI 렌더 순서**: PCT → SPEED → BAR → MSG
- [ ] `emit_progress()`가 순서 있는 필드 수용하도록 수정
- [ ] `ProgressBar._emit()`이 순서 있는 메시지 구성하도록 수정
- [ ] `log_console.py` 렌더링이 필드 순서 준수하도록 수정

#### Task 3.3: 최소 영문 MSG
- [ ] MSG에서 MB/ETA/speed 제거, 단일 단어 상태만
- [ ] speed/pct/bar_frac는 별도 구조화 필드로 유지
- [ ] TUI 렌더: `[45%] [2.3MB/s] [███░░░░░] downloading`

**완료 기준**:
- [ ] MSG 필드에만 포함: `downloading` | `completed` | `failed` | `verifying`
- [ ] TUI 컬럼 순서: PCT | SPEED | BAR | MSG
- [ ] MSG에 MB/ETA 없음 (필요시 구조화 필드로 사용 가능)

---

### Phase 4: 의존성 프로비저닝 심층 리뷰 (우선순위: 최우선)

#### Task 4.1: ProvisioningManager 리팩토링
- [ ] `ProvisioningManager` (666줄) 3개 클래스로 분리:
  - `Planner`: `resolve()` → plans
  - `Executor`: `provision(plans)` → results  
  - `Committer`: `commit(plans, results)` → manifest + overlay
- [ ] `resolver.py:154,157` 중복 `candidates.sort()` 제거

#### Task 4.2: Pot Server 로직 리뷰
- [ ] `ensure_node_server()`: 200+줄 중첩 try/except → 단계별 분리
- [ ] `npm ci` / `tsc` 타임아웃 처리: 명시적 `ProvisionResult` 에러
- [ ] Prewarm lock: `acquire_prewarm_lock()`이 `int | None` 반환 — `Result`로 표준화

#### Task 4.3: 재프로비저닝 가드
- [ ] `manager.py:744-770`: `ensure_all(stale_only=True)` — 이미 최신인 컴포넌트 스킵 검증
- [ ] 멱등성 체크 추가: 버전 X에 이미 있으면 재다운로드 안 함
- [ ] 진행률 바: 실제 다운로드/설치 시만 표시, "이미 최신"엔 표시 안 함

#### Task 4.4: Bridge 동기/비동기 경계
- [ ] `bridge.py`: sync 컨텍스트에서 `asyncio.run()` — 중첩 이벤트 루프 없는지 확인
- [ ] `update_worker.py`: `_do_upgrade()`가 매 실행마다 새 `ProvisioningManager` 생성 — 재사용 검토

**완료 기준**:
- [ ] 모든 프로비저닝 함수가 명시적 에러와 함께 `ProvisionResult` 반환
- [ ] 프로비저닝 체인에 silent fallback 없음
- [ ] 진행률 바가 실제 작업시에만 표시
- [ ] 코드 리뷰 5축 품질 게이트 통과
---

## 의존성 그래프

```
Phase 1 (yt-dlp 바이너리)
    │
    ├── Task 1.1 → Task 1.2 → Task 1.3
    │
    └── Phase 2 활성화 (updater.py 정리)

Phase 2 (Silent Fallback)
    │
    ├── Task 2.1 (감사) → Task 2.2 (수정) → Task 2.3 (계약)
    │
    ├── 의존: Phase 1 (updater.py 변경)
    │
    └── Phase 4 활성화 (프로비저닝 에러 명시적화)

Phase 3 (진행률 바)
    │
    ├── Task 3.1 → Task 3.2 → Task 3.3
    │
    └── 독립적 (Phase 2와 병렬 가능)

Phase 4 (프로비저닝 리뷰)
    │
    ├── Task 4.1 (Manager 분리)
    ├── Task 4.2 (Pot Server)
    ├── Task 4.3 (재프로비저닝 가드)
    └── Task 4.4 (Bridge)
    │
    └── 의존: Phase 2 (명시적 에러)
```

---

## 체크포인트

### 체크포인트 1: Phase 1 완료 후
- [ ] `yt-dlp` 바이너리가 `bin/` 디렉토리에만 존재
- [ ] `.pylib`에 yt-dlp 없음
- [ ] `check_deps()` + `upgrade_packages()`가 바이너리 경로 사용
- [ ] 테스트: `test_v38_contracts.py::TestEnvironmentIsolation::test_updater_cli_base_is_isolated` 통과

### 체크포인트 2: Phase 2 완료 후
- [ ] 앱 코드에 bare `except:` 제로 (grep 검증)
- [ ] 모든 실패가 F12 에러 로그와 실행 가능한 메시지 생성
- [ ] `check_deps()`가 명시적 FAIL 사유 반환
- [ ] 테스트: 모든 `test_v38_contracts.py` 통과

### 체크포인트 3: Phase 3 완료 후
- [ ] 진행률 바 MSG 최소 영문
- [ ] TUI 렌더 순서: PCT | SPEED | BAR | MSG
- [ ] MSG에 MB/ETA 없음
- [ ] F12/TUI 시각적 검증

### 체크포인트 4: Phase 4 완료 후
---

## 리스크 및 완화

| 리스크 | 영향도 | 완화 방안 |
|--------|--------|-----------|
| yt-dlp 바이너리 경로 dev vs frozen 상이 | 높음 | `_bin_dir()`가 `get_writable_base()` 사용 — 단일 SSOT |
| Silent fallback 제거가 레거시 플로우 깨뜨림 | 높음 | 명시적 에러 이벤트 추가, 각 변환 테스트 |
| 진행률 바 재구성이 TUI 렌더 깨뜨림 | 중간 | `log_console.py`가 구조화 필드 처리, 문자열 파싱 안 함 |
| ProvisioningManager 분리가 async bridge 깨뜨림 | 높음 | `bridge.py` 인터페이스 동일 유지, 내부만 리팩토링 |
| Pot server npm/tsc 타임아웃 처리 | 중간 | 명시적 `ProvisionResult.error` + stdout/stderr 캡처 |

---

## 미해결 질문

1. **바이너리 네이밍**: `yt-dlp.exe` (Windows) vs `yt-dlp` (Unix) — 현재 `_exe_suffix()`가 처리, 확인 필요
2. **Nightly 채널**: `yt-dlp-nightly` 바이너리를 GitHub nightly-builds에서 — 별도 다운로드 경로?
3. **F12 진행률 바**: F12에 PCT/SPEED/BAR 컬럼 필요한가, MSG만 필요한가? 현재 F12는 전체 이벤트 미러링
4. **`stale_only=True`**: 바이너리 컴포넌트에 대해 "이미 최신" 올바르게 감지하는가? 테스트 필요

---

## 다음 단계

1. **이 계획 승인** — 승인 시 `tasks/todo.md`에 원자적 태스크 생성
2. **Phase 1 시작** — yt-dlp 바이너리 마이그레이션 (최고 임팩트, Phase 2 차단 해제)
3. **Phase 3 병렬** — 진행률 바 재구성 (독립적)
4. **Phase 2 & 4 순차** — Fallback 제거가 깨끗한 프로비저닝 리뷰 가능하게 함