import os
import sys

results = []
for r, _, fs in os.walk('chzzktube'):
    for f in fs:
        if f.endswith('.py'):
            path = os.path.join(r, f)
            try:
                with open(path, 'r', encoding='utf-8') as fp:
                    for i, line in enumerate(fp, 1):
                        stripped = line.strip()
                        if stripped == 'except Exception:' or stripped == 'except:' or (stripped.startswith('except Exception as') and 'pass' in stripped):
                            results.append(f'{path}:{i}: {stripped}')
            except:
                pass

print('\n'.join(results[:100]))