import re

with open('chzzktube/pipeline/live_recorder.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the specific indentation issue - there's a trailing .strip(), and extra )
old = 'raw_log.raw("LIVE", f"_drain_stderr error: {type(e).__name__}: {e}", is_error=True, to_tui=False).strip(),\n                                      ),'

new = ''

if old in content:
    content = content.replace(old, new)
    with open('chzzktube/pipeline/live_recorder.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Fixed!')
else:
    print('Old text not found, searching...')
    idx = content.find('raw_log.raw("LIVE", f"_drain_stderr error:')
    if idx >= 0:
        print(repr(content[idx:idx+150]))
        # Fix with regex
        pattern = r'raw_log\.raw\("LIVE", f"_drain_stderr error: \{type\(e\)\.__name__\}: \{e\}", is_error=True, to_tui=False\)\.strip\(\),\n\s+\),'
        new_content = re.sub(pattern, '', content, flags=re.DOTALL)
        if new_content != content:
            with open('chzzktube/pipeline/live_recorder.py', 'w', encoding='utf-8') as f:
                f.write(new_content)
            print('Fixed via regex!')
        else:
            print('Regex not matched')