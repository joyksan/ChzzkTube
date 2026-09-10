import os, sys

md_files = [f for f in os.listdir('.') if f.endswith('.md')]
non_ascii = [f for f in md_files if not all(ord(c) < 128 for c in f)]
for f in sorted(non_ascii):
    print(f)
for f in sorted(md_files):
    print(f)
