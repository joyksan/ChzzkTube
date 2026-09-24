with open('chzzktube/pipeline/live_recorder.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the specific indentation issue
old = 'raw_log.raw("LIVE", f"_drain_stderr error: {type(e).__name__}: {e}", is_error=True, to_tui=False).strip(),\n                                      ),'

new = ''

if old in content:
    content = content.replace(old, new)
    with open('chzzktube/pipeline/live_recorder.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Fixed!')
else:
    print('Not found - searching with regex...')
    # Try regex
    pattern = r'raw_log\.raw\("LIVE", f"_drain_stderr error: \{type\(e\)\.__name__\}: \{e\}", is_error=True, to_tui=False\)\.strip\(\),\n\s+\),'
    match = re.search(old.replace('{', r'\{').replace('}', r'\}'), content, re.DOTALL)
    if match:
        print('Regex match found')
        content = re.sub(pattern, '', content, flags=re.DOTALL)
        with open('chzzktube/pipeline/live_recorder.py', 'w', encoding='utf-8') as f:
            f.write(content)
        print('Fixed via regex!')
    else:
        print('Regex not found')
        idx = content.find('raw_log.raw("LIVE", f"_drain_stderr error:')
        if idx >= 0:
            print(repr(content[idx:idx+150]))