with open('c:/dev/ChzzkTube/main.py','r',encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if '_wait_pot_if_needed' in line or '_force_unlock_input' in line or 'def closeEvent' in line:
        print(f'{i}: {line.rstrip()}')