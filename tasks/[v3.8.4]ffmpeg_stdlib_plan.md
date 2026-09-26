# Implementation Plan: FFmpeg stdlib-only dynamic provisioning

## Status: DONE (v3.8.4)

**검증 결과**: `340 passed` (전체 스위트), `python sync_mirrors.py --check` → `changed 0 / missing 0`,
`git diff --check` clean.

## Overview
Windows/Linux는 BtbN GitHub Releases의 최신 static GPL asset을 동적으로 선택하고, 별도 `checksums.sha256`에서 실제 asset 이름을 찾아 SHA-256을 검증한 뒤 stdlib ZIP/tar 전개를 수행한다. macOS는 Homebrew Bottle을 우선 사용하되 Formula bottle metadata의 relocatable `cellar`와 SHA-256을 검증하며, `_verify_ffmpeg` 실행 검증에 실패하면 폴백 없이 명시적 FAIL로 종료한다.

## Architecture Decisions
- GitHub Releases asset `digest`는 관찰 정보일 뿐 신뢰 루트로 사용하지 않는다. BtbN의 별도 `checksums.sha256` 텍스트와 다운로드 바이트를 비교한다.
- BtbN은 Windows `.zip`, Linux `.tar.xz` static GPL asset만 선택한다. shared/debug/source asset과 `.7z` 등 외부 도구 의존 형식은 배제한다.
- 모든 아카이브는 임시 staging 디렉터리에서 stdlib로 안전하게 전개한 뒤 검증하고, 기존 설치 디렉터리는 rollback 가능한 단계적 교체로 반영한다.
- ZIP은 정규화된 멤버 경로의 staging prefix를 엄격히 검사하고, tar는 Python 3.12 `filter="data"`를 사용한다.
- macOS Bottle은 `cellar`가 `:any` 또는 `:any_skip_relocation`인 candidate만 허용한다. `ffmpeg`/`ffprobe` 실행 검증이 통과해야 설치로 간주한다.
- macOS Bottle 실패 시 evermeet 또는 다른 Intel-only/unverified candidate로 퇴행하지 않는다. 표준 `DEPS/FFMP/FAIL`과 F12 상세 원인을 반환한다.

## 구현 매핑 (실제 코드 위치)

| 계약 | 구현 |
|---|---|
| 아키텍처 정규화 | `components._normalize_arch` |
| BtbN 에셋 선택 | `components._select_btbn_asset` |
| checksum 매니페스트 파싱 | `components._parse_btbn_checksums` |
| resolver 단일 트랜잭션 | `components._resolve_btbn_ffmpeg` |
| 안전 전개 | `components._safe_extract` |
| 바이너리 탐색 | `components._locate_binaries` |
| 원자 교체 | `components._atomic_install` |
| 수급 감사 기록 | `components._record_provision_plan` |
| macOS relocatable 게이트 | `components._ensure_ffmpeg_macos` (cellar 검사) |
| 진행 메타데이터 | `components._ffmpeg_progress_event` / `_ffmpeg_done_event` |

## Task List

### Task 1: 계획 및 계약 고정
- [x] 기존 `tasks/plan.md` 보존
- [x] FFmpeg 전용 계획과 수용 기준 기록
- [x] RED 계약 테스트 작성
- [x] RED 실행으로 현재 실패 확인

### Task 2: BtbN resolver 및 checksum manifest
- [x] Windows/Linux 아키텍처 정규화(`amd64`, `arm64`, unsupported)
- [x] BtbN latest release asset 필터링 및 정확한 static GPL asset 선택
- [x] `checksums.sha256` 파서와 정확한 asset 이름 매칭
- [x] GitHub `digest`를 신뢰값으로 사용하지 않는 계약 테스트
- [x] checksum 부재·형식 오류·해시 불일치 실패 경로

### Task 3: stdlib-only 다운로드·전개·원자 반영
- [x] 다운로드 중 SHA-256 계산 및 mismatch 시 `.part` 제거
- [x] ZIP 경로 검사 및 tar `filter="data"` 공통 helper
- [x] Windows/Unix 공통 rollback 가능한 디렉터리 교체
- [x] ffmpeg/ffprobe 존재·실행 권한·실행 검증
- [x] 외부 압축 도구·7z 의존 제거

### Task 4: macOS relocatable Homebrew Bottle
- [x] Formula JSON bottle candidate 선택 및 `cellar` 검증
- [x] Bottle SHA-256 필수 검증 (부재 시 skip)
- [x] 중첩 Cellar/bin 탐색 후 격리 캐시 `bin/` 으로 정규화
- [x] `_verify_ffmpeg` 실패 시 즉시 표준 FAIL, evermeet 폴백 제거
- [x] Apple Silicon/Intel 모두 relocatable 게이트 적용

### Task 5: 문서·정합성·최종 검증
- [x] `docs/HANDOVER.md` 갱신 (trailing whitespace 정리 포함)
- [x] `python sync_mirrors.py --check` 변경 0건/누락 0건
- [x] focused pytest, 전체 pytest(340 passed), py_compile, `git diff --check`
- [x] 최종 diff에서 기존 TUI/F12 변경 보존 확인

## Checkpoints
- [x] Task 1 RED 확인
- [x] Task 2-3 focused tests green (`tests/test_ffmpeg_resolver_contract.py`)
- [x] Task 4 macOS tests green (`tests/test_ffmpeg_archive_contract.py`, `test_v38_contracts.py`)
- [x] Task 5 전체 검증 green (340 passed)

## Risks and Mitigations
| Risk | Impact | Mitigation |
|---|---|---|
| BtbN asset/manifest 이름 변경 | 수급 실패 | 정확한 이름 매칭과 명시적 FAIL, network tests는 mock |
| tar/ZIP 악성 경로 | path traversal | staging prefix 검증과 `filter="data"`, `TarError` → `ValueError` 정규화 |
| Windows directory replace 제한 | 설치 손상 | backup/incoming/rename rollback |
| Homebrew Bottle 비재배치성 | dyld 실패 | `cellar` metadata 선검증 + `_verify_ffmpeg` |
| 기존 TUI/F12 변경과 충돌 | 회귀 | components/tests 관련 범위만 수정하고 diff 보존 |

## 구현 중 발견·해결한 함정

1. **`-gpl-` vs `-gpl.` 명명 규칙**: BtbN 자산은 `ffmpeg-master-latest-win64-gpl.zip`
   형태로 `-gpl-`가 존재하지 않는다. `"gpl" in name` + `"shared" not in name`으로 교정.
2. **`tarfile.OutsideDestinationError`는 `ValueError`가 아니다**: `FilterError`→`TarError`
   계열이므로 호출자 계약(ValueError)에 맞춰 정규화했다.
3. **`_lzma` 부재 환경**: 일부 pyenv 빌드에 `_lzma`가 없다. 모듈 최상단 `import lzma`는
   수급 모듈 전체 import를 붕괴시키므로 제거하고 `tarfile`에 위임한다.
4. **`manifest.record_install`은 존재하지 않는다**: `ProvisionManifest.load/save` +
   `ComponentRecord` + `update_component`가 유일한 공식 API다.
5. **테스트 mock의 무한 read**: `read()`가 항상 같은 payload를 반환하면 다운로드 루프가
   종료되지 않아 `No space left on device`로 이어진다. offset 기반 소진형 스텁이 필요하다.
6. **`emit_component`가 진행 메타데이터를 못 받음**: `component_id`/`is_progress`
   파라미터를 추가해야 §3.7-5 갱신형 계약이 브리지까지 도달한다.

## Open Questions
- live BtbN/Homebrew API 테스트는 CI flake 방지를 위해 mock 기반으로 격리한다.

- GitHub Releases asset `digest`는 관찰 정보일 뿐 신뢰 루트로 사용하지 않는다. BtbN의 별도 `checksums.sha256` 텍스트와 다운로드 바이트를 비교한다.
- BtbN은 Windows `.zip`, Linux `.tar.xz` static GPL asset만 선택한다. shared/debug/source asset과 `.7z` 등 외부 도구 의존 형식은 배제한다.
- 모든 아카이브는 임시 staging 디렉터리에서 stdlib로 안전하게 전개한 뒤 검증하고, 기존 설치 디렉터리는 rollback 가능한 단계적 교체로 반영한다.
- ZIP은 정규화된 멤버 경로의 staging prefix를 엄격히 검사하고, tar는 Python 3.12 `filter="data"`를 사용한다.
- macOS Bottle은 `cellar`가 `:any` 또는 `:any_skip_relocation`인 candidate만 허용한다. Bottle 전체를 격리 Homebrew prefix 구조로 전개하며 `ffmpeg`/`ffprobe` 실행 검증이 통과해야 설치로 간주한다.
- macOS Bottle 실패 시 evermeet 또는 다른 Intel-only/unverified candidate로 퇴행하지 않는다. 표준 `DEPS/FFMP/FAIL`과 F12 상세 원인을 반환한다.

## Task List

### Task 1: 계획 및 계약 고정
- [x] 기존 `tasks/plan.md` 보존
- [x] FFmpeg 전용 계획과 수용 기준 기록
- [ ] RED 계약 테스트 작성
- [ ] RED 실행으로 현재 실패 확인

### Task 2: BtbN resolver 및 checksum manifest
- [ ] Windows/Linux 아키텍처 정규화(`amd64`, `arm64`, unsupported)
- [ ] BtbN latest release asset 필터링 및 정확한 static GPL asset 선택
- [ ] `checksums.sha256` 파서와 정확한 asset 이름 매칭
- [ ] GitHub `digest`를 신뢰값으로 사용하지 않는 계약 테스트
- [ ] checksum 부재·형식 오류·해시 불일치 실패 경로

### Task 3: stdlib-only 다운로드·전개·원자 반영
- [ ] 다운로드 중 SHA-256 계산 및 mismatch 시 `.part` 제거
- [ ] ZIP 경로 검사 및 tar `filter="data"` 공통 helper
- [ ] Windows/Unix 공통 rollback 가능한 디렉터리 교체
- [ ] ffmpeg/ffprobe 존재·실행 권한·실행 검증
- [ ] 외부 압축 도구·7z 의존 제거

### Task 4: macOS relocatable Homebrew Bottle
- [ ] Formula JSON bottle candidate 선택 및 `cellar` 검증
- [ ] Bottle SHA-256 검증
- [ ] Bottle 전체를 격리 prefix로 전개
- [ ] `_verify_ffmpeg` 실패 시 즉시 표준 FAIL, evermeet 폴백 제거
- [ ] Apple Silicon에서 Intel-only candidate 차단

### Task 5: 문서·정합성·최종 검증
- [ ] `docs/HANDOVER.md`, `docs/CHANGELOG.md` 갱신
- [ ] `python sync_mirrors.py --check` 변경 0건/누락 0건
- [ ] focused pytest, 전체 pytest, compileall, `git diff --check`
- [ ] 최종 diff에서 기존 TUI/F12 변경 보존 확인

## Checkpoints
- [ ] Task 1 RED 확인
- [ ] Task 2-3 focused tests green
- [ ] Task 4 macOS tests green
- [ ] Task 5 전체 검증 green

## Risks and Mitigations
| Risk | Impact | Mitigation |
|---|---|---|
| BtbN asset/manifest 이름 변경 | 수급 실패 | 정확한 이름 매칭과 명시적 FAIL, network tests는 mock |
| tar/ZIP 악성 경로 | path traversal | staging prefix 검증과 `filter="data"` |
| Windows directory replace 제한 | 설치 손상 | backup/incoming/rename rollback |
| Homebrew Bottle 비재배치성 | dyld 실패 | `cellar` metadata 선검증 + `_verify_ffmpeg` |
| 기존 TUI/F12 변경과 충돌 | 회귀 | components/tests 관련 범위만 수정하고 diff 보존 |

## Open Questions
- live BtbN/Homebrew API 테스트는 CI flake 방지를 위해 mock 기반으로 격리한다.
