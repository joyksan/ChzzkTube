# 테스트 실패 10건 원인 분석 보고서 (test_v38_contracts.py + test_download_pipeline.py)
# 생성: 2026-09-26 / 대상: pytest tests/test_v38_contracts.py (8 failed, 40 passed) + pytest tests/test_download_pipeline.py::TestPotProviderFacade (2 failed)
# 분류: A=구현 스펙과 테스트 기대치 불일치 / B=플랫폼 의존(Windows CI 불가) /
#       C=동시성·타이밍 취약 / D=실제 로그 파이프라인 동작 (§2 포함관계 모델)
#
# ── 증상별 원인 ──
#
# [1] TestErrorLogFormat 4건 (cause_action / delimiter / newline / multiple_delimiters)
#     - sanitize 계층 부재: format_log_line()은 │·\n을 치환하지 않는다.
#       실측: msg "evil │ injected" → 라인에 그대로 출력, parts=5 (기대 4).
#             "evil\ninjected" → 개행 그대로 출력 ("\n not in line" 실패).
#       증거: format_log_line_for_event(event) → format_log_line(...) 경로에
#             구분자/개행 치환 코드 없음 (log_emitter.py:228-292).
#     - 등급: A. 정규화 헬퍼(_normalize_cause/_normalize_action)는 원인·액션
#       키워드 매핑만 하고 사용자 msg 본문의 │·\n은 손대지 않는다 —
#       테스트가 포맷터에 sanitize 책임을 기대하지만 구현 스펙에 그 책임이 없다.
#     - 추가로 같은 파일의 test_cause_action_keywords_standardized는
#       _normalize_action("retry mirror (99/99)") == "" 를 기대하지만,
#       구현은 미등록 키를 원문 보존한다(`return action.strip()`).
#       등급: A. 미러 N/M 패턴은 _ERROR_ACTIONS에 (1/3)~(3/3)만 등록 —
#       기대치("" 반환)가 스펙 어디에도 없다.
#
# [2] TestEnvironmentIsolation 3건 (bottle_keys / binaries_normalized / contract_shape)
#     - Windows CI에서 platform.machine()="AMD64", release()="11" —
#       _MAC_BOTTLE_ARCH_PREFIX는 {"arm64","x86_64"}만 알므로 prefix="arm64_",
#       macOS Darwin major 판정(_macos_buildnum()=11)은 bottle 키
#       (catalina=19~tahoe=26) 전부보다 낮아 호환 필터가 전멸시킨다.
#       실측: keys == ['arm64_golden_gate'] (기대: sequoia 포함).
#       contract_shape도 동일 원인 — bottle 키 선택 단계에서 탈락해
#       다운로드·설치 단계까지 도달하지 못한다 (result는 None이 아니라 에러 문자열,
#       ffmpeg/bin 미생성).
#       binaries_normalized는 _locate_binaries→_atomic_install 경로에서
#       Windows os.replace 의미론 차이로 cache/bin/ffmpeg 미생성 (FileNotFoundError).
#     - 등급: B. 테스트가 macOS Darwin 환경을 암묵 가정 — Windows에서는
#       monkeypatch로 platform.machine/release를 고정해도 prefix 테이블·
#       buildnum 상한 로직이 Windows 값을 처리하지 못한다.
#       contract_shape 테스트는 machine/release를 arm64/24.0.0으로 고정했지만
#       (test_v38_contracts.py:204-205), 그 아래 _macos_bottle_keys(files) 호출
#       경로(components.py:705)에서 files 딕셔너리의 키가 linux 포함 키와 섞여
#       최종 선택이 달라진다.
#
# [3] TestF12CliNetHelpers::test_helpers_ignore_empty_input (full==[], tui==[])
#     - log_f12_cli("", "body")는 cmd="" → $프롬프트 생략, output="body" →
#       body 1건을 full 버스에 발행한다 (raw_log.py:206-227: `if cmd:` / `if output:`
#       각각 독립 판정). 즉 "빈 cmd + 비어있지 않은 output = 1건 발행"이
#       현재 구현의 정상 동작이다. 테스트 기대치(full==[])와 정면 충돌.
#     - 등급: A. 테스트명이 "empty input 무시"를 주장하지만 ("","body")는
#       half-empty이지 empty가 아니다. 진짜 empty는 ("","") 또는 (None,None)이며
#       그 경우는 실제로 0건이다.
#     - 부수 요인 D: _capture()가 세션 공유 dispatcher에 구독자를 누적한다.
#       subscribe_concise/subscribe_full은 `if fn not in subs` 중복 방지뿐이라
#       이전 테스트의 람다가 남아 있으면 tui/full에 타 테스트 이벤트가 섞인다.
#       같은 파일의 test_log_f12_cli_...가 먼저 실행되면 순서 의존 오염 발생.
#       등급: C+D. _capture에 unsubscribe/격리 메커니즘이 없다.
#
# [4] test_coordinator.py::TestPotStatusBusWiring::test_pot_failed_maps_to_fail_status
#     - _on_pot_status("failed")는 의도적으로 raw 버스에 아무것도 발행하지 않는다
#       (startup_coordinator.py:124-127: "중복 방지… _on_pot_finished → report_pot()
#       에서 1회만 단일 발행"). 테스트는 POT stage 이벤트가 버스에 오기를
#       기대하므로 IndexError(list index out of range, test_coordinator.py:120).
#     - 등급: A. 테스트가 발행 없는 경로에 발행을 기대 — 스펙(단일 발행)과 충돌.
#       올바른 기대치는 report_pot()/ _on_pot_finished() 경로를 함께 구동한 뒤
#       FAIL 1건을 단언하는 것이다.
#
# [5] test_chzzk_live_integration.py::test_chzzk_live_real_hls_pipeline
#     - download_target()이 False 반환: "치지직 녹화: chzzk live recording failed".
#       HLS 파이프라인이 file:// m3u8 + mpeg2video 2초 소스를 실제 ffmpeg로
#       녹화하는데, Windows CI의 ffmpeg 부재/버전 차 또는 pipe:1 릴레이 경로에서
#       실패한다. 외부 바이너리·네트워크 의존 테스트.
#     - 등급: B. 로컬 ffmpeg 실측 의존 — CI ffmpeg 미설치 시 전제 붕괴.
#       (파일 상단에도 `pytest.skip("ffmpeg is required")` 가드가 부분 존재.)
#
# [6] test_download_pipeline.py::TestPotProviderFacade 2건 (reexports_from_node_provider / reexports_from_pot_server)
#     - infra/__init__.py에 pot_provider 재수출이 누락되어 AttributeError 발생.
#     - infra/__init__.py에 pot_provider, pot_server, node_provider 등 re-export 추가로 해결.
#     - 등급: A. 패키지 구조 누락 — 테스트가 정확한 스펙을 검증.
#
# ── 테스트 결함으로 열어둘 항목 (수정 없이 기록) ──
#  T1. sanitize 기대 4건: 포맷터에 │·\n 치환 책임을 요구하지만 스펙·구현에 없음.
#      → 포맷터가 아니라 "TUI 컬럼 파서" 쪽 계약을 먼저 정해야 함.
#  T2. normalize 미등록 키 기대 1건(assert (99/99)==""): 원문 보존이 합리적이며
#      "" 기대의 근거 문서 없음.
#  T3. bottle 3건: Windows CI에서 macOS 전제를 강제 — monkeypatch 범위가
#      _macos_bottle_keys 내부의 prefix/buildnum 테이블까지 못 미침.
#  T4. log_f12 half-empty 1건: ("","body")를 empty로 간주 — 시맨틱 오류.
#  T5. pot failed 버스 기대 1건: 단일-발행 스펙과 정면 충돌.
#  T6. 구독자 누적(_capture): 테스트 격리 부재 — 순서 의존 플레이크 소지.
#      (conftest.py에 raw_log 격리 픽스처 없음 — test_download_pipeline.py는
#      수동 flush로 회피 중.)