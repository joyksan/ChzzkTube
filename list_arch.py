import os

base = os.getcwd()
for name in os.listdir('.'):
    if not name.endswith('.md'):
        continue
    if '아키텍처' in name or '구조' in name:
        path = os.path.join(base, name)
        with open(path, 'rb') as f:
            data = f.read()
        out = path + '\n' + '=' * 80 + '\n'
        out += data.decode('utf-8', errors='replace')
        with open('arch_dump.txt', 'w', encoding='utf-8') as out_f:
            out_f.write(out)
        print('written:', path)
        break
else:
    print('not found', flush=True)
