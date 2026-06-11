import ast, sys, pathlib
fails = []
for p in pathlib.Path("src/footstats").rglob("*.py"):
    try: ast.parse(p.read_text(encoding="utf-8"))
    except SyntaxError as e: fails.append(f"{p}: {e}")
if fails:
    print("SYNTAX ERRORS:"); [print(f) for f in fails]; sys.exit(1)
print(f"OK: {len(list(pathlib.Path('src/footstats').rglob('*.py')))} files")
