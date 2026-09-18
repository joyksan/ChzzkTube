# Agent Skills Quick Reference

프로젝트 내 `.skills/`에 구성된 엔지니어링 및 코드베이스 분석 스킬 요약 레퍼런스입니다. Cline 채팅창에서 슬래시 커맨드(`/command`)로 호출할 수 있습니다.

---

### 1. 코드베이스 아키텍처 및 지식 그래프 (Understand-Anything)

* **`/understand` (핵심)**
  * 경로: `.skills/understand-anything/understand/SKILL.md`
  * 역할: 저장소 전체 정적 분석, 모듈별 책임 분할, Mermaid 아키텍처 다이어그램 및 `.ua/knowledge-graph.json` 지식 그래프 생성
  * 권장 시점: 프로젝트 구조 파악, 리팩토링 전 전체 시스템 의존성 매핑

* **`/understand-dashboard`**
  * 경로: `.skills/understand-anything/understand-dashboard/SKILL.md`
  * 역할: 생성된 지식 그래프를 브라우저에서 대화형(Interactive) 노드 맵으로 시각화하는 UI 구동
  * 권장 시점: GUI 환경에서 컴포넌트 간 연결 관계를 마우스로 직접 탐색할 때

* **`/understand-explain`**
  * 경로: `.skills/understand-anything/understand-explain/SKILL.md`
  * 역할: 특정 모듈, 워커 스레드, 데이터 흐름의 동작 메커니즘 딥다이브 분석
  * 권장 시점: 복잡한 다운로드/파싱 파이프라인 등 특정 로직의 내부 순서를 집중 파악할 때

* **`/understand-domain`**
  * 경로: `.skills/understand-anything/understand-domain/SKILL.md`
  * 역할: 파일 경로 기준이 아닌 비즈니스 도메인 관점(미디어 수집, 포맷 변환 등)의 데이터 흐름 추출
  * 권장 시점: 기획 요구사항이 실제 어떤 코드 흐름으로 실현되는지 대조할 때

* **`/understand-diff`**
  * 경로: `.skills/understand-anything/understand-diff/SKILL.md`
  * 역할: Git 변경점이 전체 시스템에 미치는 영향도 및 파급 효과(Ripple Effect) 사전 분석
  * 권장 시점: 공통 모듈 수정 후 사이드 이펙트 범위 점검

* **`/understand-onboard`**
  * 경로: `.skills/understand-anything/understand-onboard/SKILL.md`
  * 역할: 신규 기여자를 위한 실행 흐름 기반의 단계별 코드 투어 문서 생성
  * 권장 시점: 저장소 온보딩 문서 구축 및 핵심 진입점 가이드 작성

* **`/understand-chat`**
  * 경로: `.skills/understand-anything/understand-chat/SKILL.md`
  * 역할: 구축된 지식 그래프 캐시 기반의 고정밀 코드베이스 질의응답
  * 권장 시점: 특정 클래스나 함수가 프로젝트 어디에서 참조되는지 빠르게 검색할 때

* **`/understand-knowledge`**
  * 경로: `.skills/understand-anything/understand-knowledge/SKILL.md`
  * 역할: 프로젝트 내 흩어진 마크다운 메모, 설계 문서(ADR), 핸드오버 파일의 연결 관계 그래프 구성
  * 권장 시점: 문서 간 모순 확인 및 기술 문서 인덱싱

* **`/understand-figma`**
  * 경로: `.skills/understand-anything/understand-figma/SKILL.md`
  * 역할: UI 디자인 구조와 프론트엔드/GUI 코드 컴포넌트 매핑
  * 권장 시점: 화면 레이아웃 설계를 코드로 이식할 때

---

### 2. 기획 및 설계 (Ideation & Specification)

* **`/context` (맥락 정리)**
  * 경로: `.skills/context-engineering/SKILL.md`
  * 역할: 긴 대화 로그나 이전 세션의 잡담을 쳐내고 현재 코드 상태와 잔여 작업만 Ground Truth로 동기화
  * 권장 시점: 이전 대화 세션을 붙여넣고 작업을 이어갈 때 최우선 실행

* **`/plan` (작업 분할)**
  * 경로: `.skills/planning-and-task-breakdown/SKILL.md`
  * 역할: 목표 기능을 15~30분 단위의 독립적이고 검증 가능한 작업 체크리스트로 분해
  * 권장 시점: 대규모 기능 구현 전 순차 작업 목록 도출

* **`/spec` (스펙 정의)**
  * 경로: `.skills/spec-driven-development/SKILL.md`
  * 역할: 코드 작성 전 데이터 모델, API 시그니처, 수용 기준(Acceptance Criteria) 명문화
  * 권장 시점: 에이전트의 임의 판단 및 엉뚱한 코드 생성 방지

* **`/idea` (아이디어 정체)**
  * 경로: `.skills/idea-refine/SKILL.md`
  * 역할: 추상적인 요구사항을 기술적 개발 목표와 구현 범위로 구체화

* **`/interview` (요구사항 발굴)**
  * 경로: `.skills/interview-me/SKILL.md`
  * 역할: 에이전트가 개발자에게 역질문하여 숨겨진 엣지 케이스와 제약 조건 도출

* **`/api` (인터페이스 설계)**
  * 경로: `.skills/api-and-interface-design/SKILL.md`
  * 역할: 결합도가 낮고 호출자 관점에서 명확한 API/함수 규격 선제 정의

---

### 3. 구현 및 테스트 (Build & Test)

* **`/build` (점진적 구현)**
  * 경로: `.skills/incremental-implementation/SKILL.md`
  * 역할: 대량 수정을 지양하고 작은 단위(Slice)로 나누어 빌드 성공을 유지하며 코딩
  * 권장 시점: 신규 기능 구현 단계

* **`/tdd` 또는 `/test` (테스트 주도 개발)**
  * 경로: `.skills/test-driven-development/SKILL.md`
  * 역할: 실패 테스트(Red) -> 최소 구현(Green) -> 리팩토링 사이클 강제
  * 권장 시점: 핵심 로직 안정성 확보 및 결함 방지

* **`/ui` (UI 엔지니어링)**
  * 경로: `.skills/frontend-ui-engineering/SKILL.md`
  * 역할: 정상 화면 외에 로딩, 에러, 빈 상태, 접근성 및 레이아웃 엣지 케이스 반영

* **`/browser-test` (개발자 도구 검증)**
  * 경로: `.skills/browser-testing-with-devtools/SKILL.md`
  * 역할: 렌더링 결함, 콘솔 에러, 네트워크 통신 실패 실시간 추적

---

### 4. 검증, 보안 및 성능 (Review & Hardening)

* **`/review` (코드 품질 검증)**
  * 경로: `.skills/code-review-and-quality/SKILL.md`
  * 역할: 가독성, 결합도, 에러 핸들링 등 엄격한 5대 축 기반 정량 평가

* **`/security` (보안 점검)**
  * 경로: `.skills/security-and-hardening/SKILL.md`
  * 역할: 입력값 검증 누락, 인젝션 취약점, 민감 정보 노출 및 권한 결함 점검

* **`/doubt` (전제 조건 의심)**
  * 경로: `.skills/doubt-driven-development/SKILL.md`
  * 역할: 정상 작동하는 코드의 동시성 결함, 레이스 컨디션, 극단적 실패 시나리오 추적

* **`/perf` (성능 최적화)**
  * 경로: `.skills/performance-optimization/SKILL.md`
  * 역할: 추측성 튜닝을 배제하고 프로파일링 지표 기반의 CPU/메모리 병목 해소

---

### 5. 리팩토링 및 디버깅 (Refactoring & Recovery)

* **`/simplify` (단순화)**
  * 경로: `.skills/code-simplification/SKILL.md`
  * 역할: 불필요한 추상화 계층, 오버엔지니어링된 디자인 패턴 및 중복 코드 제거

* **`/debug` (가설 기반 디버깅)**
  * 경로: `.skills/debugging-and-error-recovery/SKILL.md`
  * 역할: 땜질식 수정 금지, 가설 수립 -> 최소 재현 -> 근본 원인 규명 순차 진행

* **`/constraint` (제약 기반 개발)**
  * 경로: `.skills/constraint-driven-development/SKILL.md`
  * 역할: 메모리 제한, 서드파티 라이브러리 사용 제한 등 엄격한 시스템 조건 하에 해결책 도출

* **`/migrate` (마이그레이션)**
  * 경로: `.skills/deprecation-and-migration/SKILL.md`
  * 역할: 하위 호환성을 유지하며 노후화된 인터페이스를 안전하게 단계별 교체

---

### 6. 운영 및 배포 (Ops & Shipping)

* **`/git` (버전 관리)**
  * 경로: `.skills/git-workflow-and-versioning/SKILL.md`
  * 역할: 원자적 커밋 구성, Conventional Commits 규격 준수, 유의적 버전 관리

* **`/cicd` (자동화 파이프라인)**
  * 경로: `.skills/ci-cd-and-automation/SKILL.md`
  * 역할: GitHub Actions 빌드, 린터, 테스트 자동화 스크립트 작성 및 수정

* **`/ship` (배포 전 검증)**
  * 경로: `.skills/shipping-and-launch/SKILL.md`
  * 역할: 미커밋 파일, 환경 변수, 롤백 계획 등 최종 체크리스트 점검

* **`/observe` (관측성 확보)**
  * 경로: `.skills/observability-and-instrumentation/SKILL.md`
  * 역할: 구조화된 로깅(Structured Logging), 메트릭 수집 지점 계측

---

### 7. 문서 및 메타 (Docs & Meta)

* **`/docs` (문서화)**
  * 경로: `.skills/documentation-and-adrs/SKILL.md`
  * 역할: 기술적 의사결정 기록(ADR) 작성 및 README 동기화

* **`/sources` (출처 검증)**
  * 경로: `.skills/source-driven-development/SKILL.md`
  * 역할: 공식 문서 원본 및 오픈소스 코드를 교차 검증하여 AI 환각 차단

---

### 사용 가이드라인

* **단일 실행 우선:** 아키텍처 분석은 `/understand` 단독 호출로 충분합니다.
* **동시 조합 권장 한도:** 한 턴에 최대 2개 스킬까지만 조합하는 것이 안전합니다. (`/context /plan`, `/review /security`, `/build /tdd`)
* **단계적 파이프라인 권장:** 설계(`/spec`) -> 구현(`/build`) -> 검증(`/review`) 단계는 한 프롬프트에 몰아서 쓰지 않고 턴을 나누어 순차 실행합니다.