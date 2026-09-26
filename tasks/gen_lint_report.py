"""린트 이슈 목록 리포트 생성기 (읽기 전용 — 소스 코드는 건드리지 않는다).

ruff JSON 출력을 룰별/파일별로 집계해 tasks/lint_report.md 를 만든다.

사용:
    uv run ruff check chzzktube tests main.py --output-format=json > ruff_src.json
    uv run python tasks/gen_lint_report.py ruff_src.json
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

# 룰 → (이름, 권장 조치) — 리포트 가독성용
RULE_NOTES: dict[str, tuple[str, str]] = {
    "BLE001": ("blind-except", "`except Exception` 광범위 포착 → 구체 예외/사유+noqa"),
    "S110": ("try-except-pass", "예외를 무음으로 삼킴 → 최소한 진단 1줄 남기기"),
    "S112": ("try-except-continue", "예외 후 continue → 실패 원인 은폐 여부 검토"),
    "PLR0402": ("manual-from-import", "`import x.y as z` → `from x import y`"),
    "F401": ("unused-import", "미사용 import 제거 (자동 수정 가능)"),
    "F811": ("redefined-while-unused", "이름 재정의 — 앞 정의가 죽은 코드"),
    "F841": ("unused-variable", "미사용 지역 변수 제거"),
    "F823": ("undefined-local", "지역변수 참조 오류 — 실제 버그 가능성 높음"),
    "I001": ("unsorted-imports", "import 블록 정렬 (자동 수정 가능)"),
    "UP045": ("non-pep604-annotation-optional", "`Optional[X]` → `X | None`"),
    "UP035": ("deprecated-import", "deprecated 모듈 import → 신규 위치"),
    "UP006": ("non-pep585-annotation", "`typing.List` 등 → `list` 내장 제네릭"),
    "UP012": ("unnecessary-encode-utf8", "`.encode('utf-8')` 불필요"),
    "UP022": ("replace-stdout-stderr", "`Popen(stdout=PIPE)` → `capture_output`"),
    "PLW1510": ("subprocess-run-without-check", "`subprocess.run`에 `check=` 필요"),
    "SIM102": ("collapsible-if", "중첩 if 병합 가능"),
    "SIM114": ("if-with-same-arms", "동일 분기 병합 가능"),
    "SIM115": ("open-file-with-context-handler", "`open` → `with` 문 사용"),
    "RUF059": ("unused-unpacked-variable", "unpacking 미사용 변수 → `_` 처리"),
    "RUF012": ("mutable-class-default", "가변 클래스 기본값 → `ClassVar`"),
    "RUF013": ("implicit-optional", "암묵적 Optional → 명시적 `| None`"),
    "RUF100": ("unused-noqa", "불필요한 noqa 제거 (자동 수정 가능)"),
    "RUF022": ("unsorted-dunder-all", "`__all__` 정렬"),
    "RUF023": ("unsorted-dunder-slots", "`__slots__` 정렬"),
    "RUF046": ("unnecessary-cast-to-int", "`int()` 캐스트 불필요"),
    "RET501": ("unnecessary-return-none", "`return None` 불필요"),
    "TRY203": ("useless-try-except", "예외 핸들러가 즉시 re-raise → 제거"),
    "TRY201": ("verbose-raise", "`raise e` → `raise`"),
    "F541": ("f-string-missing-placeholders", "placeholder 없는 f-string"),
    "FURB167": ("regex-flag-alias", "`re.I` → `re.IGNORECASE`"),
    "FURB122": ("for-loop-writes", "for 루프 write → writelines 등"),
    "PLR1711": ("useless-return", "함수 끝 불필요한 return"),
    "PIE790": ("unnecessary-placeholder", "불필요한 `pass`/`...`"),
    "PIE800": ("unnecessary-spread", "불필요한 `**{}` 스프레드"),
    "PLC0206": ("dict-index-missing-items", "dict 순회 시 `.items()` 사용"),
    "C408": ("unnecessary-collection-call", "`dict()` → `{}`"),
    "C402": ("unnecessary-generator-dict", "불필요한 generator→dict"),
    "DTZ005": ("call-datetime-now-without-tzinfo", "`datetime.now()` tz 미지정"),
    "FLY002": ("static-join-to-f-string", "`''.join([...])` → f-string"),
}

# 위험도 등급
HIGH_RISK = {"F823", "F811", "PLW1510", "SIM115", "RUF012", "DTZ005", "PLC0206", "F841"}
SILENT_EXC = {"BLE001", "S110", "S112", "TRY203"}
MECHANICAL = {
    "I001", "F401", "PLR0402", "UP006", "UP012", "UP035", "UP045",
    "RUF100", "RUF022", "RUF023", "RET501", "PIE790", "PIE800",
    "F541", "FURB167", "C408", "RUF046", "PLR1711", "FURB122", "UP022",
}



def load(path: str) -> list[dict]:
    raw = Path(path).read_text(encoding="utf-8-sig")
    return json.loads(raw)


def main() -> int:
    json_path = sys.argv[1] if len(sys.argv) > 1 else "ruff_src.json"
    issues = load(json_path)

    by_rule: collections.Counter = collections.Counter(i["code"] for i in issues)
    by_file: collections.Counter = collections.Counter(i["filename"] for i in issues)
    combo: dict[tuple[str, str], list[dict]] = collections.defaultdict(list)
    for it in issues:
        combo[(it["filename"], it["code"])].append(it)

    total, files = len(issues), len(by_file)

    def bucket(codes: set[str]) -> int:
        return sum(c for r, c in by_rule.items() if r in codes)

    out: list[str] = []
    out.append("# Ruff 린트 이슈 전수 목록")
    out.append("")
    out.append("읽기 전용 리포트 — 이 문서는 소스를 수정하지 않고 현황만 기록한다.")
    out.append("")
    out.append("## 요약")
    out.append("")
    out.append(f"- **총 이슈**: {total}건")
    out.append(f"- **영향 파일**: {files}개")
    out.append(f"- **룰 종류**: {len(by_rule)}종")
    out.append("")
    out.append("### 위험도 분류")
    out.append("")
    out.append("| 등급 | 건수 | 의미 |")
    out.append("|---|---:|---|")
    out.append(f"| HIGH | {bucket(HIGH_RISK)} | 실제 버그 가능성 (미정의/죽은 코드) |")
    out.append(f"| SILENT | {bucket(SILENT_EXC)} | 예외 무음 은폐 (디버깅 불가 위험) |")
    out.append(f"| MECH | {bucket(MECHANICAL)} | 기계적 정리 (자동 수정 가능) |")
    rest = total - bucket(HIGH_RISK) - bucket(SILENT_EXC) - bucket(MECHANICAL)
    out.append(f"| 기타 | {rest} | 스타일/관용 개선 |")
    out.append("")
    out.append("## 룰별 집계")
    out.append("")
    out.append("| 룰 | 건수 | 이름 | 권장 조치 |")
    out.append("|---|---:|---|---|")
    for rule, cnt in by_rule.most_common():
        name, note = RULE_NOTES.get(rule, ("-", "-"))
        out.append(f"| `{rule}` | {cnt} | {name} | {note} |")
    out.append("")
    out.append("## 파일별 집계 (Top 40)")
    out.append("")
    out.append("| 파일 | 건수 |")
    out.append("|---|---:|")
    for fn, cnt in by_file.most_common(40):
        out.append(f"| `{fn}` | {cnt} |")
    out.append("")
    emit_high_risk(out, issues, by_rule)
    emit_silent(out, issues)
    emit_matrix(out, combo, by_file)

    Path("tasks/lint_report.md").write_text("\n".join(out), encoding="utf-8")
    print(f"wrote tasks/lint_report.md ({total} issues, {files} files)")
    return 0


def emit_high_risk(
    out: list[str], issues: list[dict], by_rule: collections.Counter
) -> None:
    out.append("## HIGH 위험 상세 (실제 버그 후보)")
    out.append("")
    if not any(r in HIGH_RISK for r in by_rule):
        out.append("_없음_")
        out.append("")
        return
    for rule in sorted(HIGH_RISK):
        if rule not in by_rule:
            continue
        name, note = RULE_NOTES.get(rule, ("-", "-"))
        items = [i for i in issues if i["code"] == rule]
        out.append(f"### `{rule}` ({name}) — {len(items)}건")
        out.append("")
        out.append(note)
        out.append("")
        out.append("| 파일 | 행 | 내용 |")
        out.append("|---|---:|---|")
        for it in sorted(items, key=lambda i: (i["filename"], i["location"]["row"])):
            snippet = (it.get("message") or "").replace("|", "\\|")
            out.append(f"| `{it['filename']}` | {it['location']['row']} | {snippet} |")
        out.append("")


def emit_silent(out: list[str], issues: list[dict]) -> None:
    out.append("## SILENT 예외 은폐 상세")
    out.append("")
    out.append("> `_warn`(platform) 패턴처럼 **삼키되 사유를 남기는** 방식 권장.")
    out.append("")
    out.append("| 파일 | 행 | 룰 | 내용 |")
    out.append("|---|---:|---|---|")
    silent = [i for i in issues if i["code"] in SILENT_EXC]
    silent.sort(key=lambda i: (i["filename"], i["location"]["row"]))
    for it in silent:
        snippet = (it.get("message") or "").replace("|", "\\|")
        loc = f"{it['location']['row']}"
        out.append(
            f"| `{it['filename']}` | {loc} | `{it['code']}` | {snippet} |"
        )
    out.append("")


def emit_matrix(out: list[str], combo: dict, by_file: collections.Counter) -> None:
    out.append("## 파일 × 룰 매트릭스 (이슈 있는 파일 전부)")
    out.append("")
    for fn, cnt in by_file.most_common():
        rules = sorted({r for (f, r) in combo if f == fn})
        detail = ", ".join(f"`{r}`x{len(combo[(fn, r)])}" for r in rules)
        out.append(f"- `{fn}` — **{cnt}** : {detail}")
    out.append("")


if __name__ == "__main__":
    raise SystemExit(main())
