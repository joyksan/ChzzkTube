path = r'c:\dev\ChzzkTube\log_console.py'
text = open(path, 'r', encoding='utf-8', newline='').readlines()
lines = [l.rstrip('\r\n') for l in text]

# 1. 클래스 끝(class)부터 display_width() 앞까지 거대 빈 줄 압축
# display_width 함수는 line 537 (현재). 그 직전까지 빈 줄을 1개로.
# 일단 display_width 정의 위치 다시 찾기
dw_idx = None
for i, l in enumerate(lines):
    if l.startswith('def display_width('):
        dw_idx = i
        break
print(f"display_width at line {dw_idx+1}")

# dw_idx 이전 빈 블록을 1줄로 압축
# 거슬러 올라가면서 연속 빈 줄을 만나면 모두 삭제 (단 마지막 빈 1줄은 유지)
i = dw_idx - 1
# 파일 끝방향으로 빈 줄 영역
blank_start = dw_idx
while blank_start > 0 and lines[blank_start - 1] == '':
    blank_start -= 1
print(f"blank block: {blank_start+1} ~ {dw_idx} (count={dw_idx-blank_start})")
# blank_start부터 dw_idx까지를 빈 줄 0개로 만들기 (display_width 직전엔 빈 줄 1개만)
# 즉 lines[dw_idx-1] = '' 한 줄로 만들고 나머지 삭제
for k in range(blank_start, dw_idx - 1):
    lines[k] = '' if k == dw_idx - 1 else ''  # 어차피 빈 줄
# 그냥 직접
# blank_start ~ dw_idx-1 까지 다 지우고 dw_idx-1 자리에 '' 하나
new_block = ['']
lines = lines[:blank_start] + new_block + lines[dw_idx:]

# 2. format_tree_item 내부 빈 줄 정리
text = '\n'.join(lines)
# fix_tree_item 본문 시작 부분: '    clean_label = str(label).replace' 직전
text = text.replace(
    '    prefix = f"{clean_label}: "\n\n\n\n    chunks = _wrap_by_width(',
    '    prefix = f"{clean_label}: "\n    chunks = _wrap_by_width('
)
# 3. emit_component 함수 본문 뒤에 죽은 docstring/if/elif 잔재 제거
text = text.replace(
    '        msg=msg,\n    )\n    """컬럼 로그 라인의 색상 — STATUS 기반 단색 분기."""\n    if " │ FAIL" in line:\n        return [(line, theme.LOG_COLOR_ERROR)]\n    if " │ WARN" in line:\n        return [(line, theme.LOG_COLOR_WARN)]\n    if " │ ABORT" in line:\n        return [(line, theme.LOG_COLOR_WARN)]\n    if " │ DONE" in line or " │ OK " in line or " │ END" in line or " │ READY" in line:\n        return [(line, theme.LOG_COLOR_SUCCESS)]\n    if " │ RUN" in line:\n        return [(line, theme.LOG_COLOR_ACCENT)]\n    return [(line, theme.LOG_COLOR_INFO)]',
    '        msg=msg,\n    )\n'
)

with open(path, 'w', encoding='utf-8', newline='') as f:
    f.write(text.replace('\n', '\r\n'))

print('done. New total lines:', len(text.split('\n')))
