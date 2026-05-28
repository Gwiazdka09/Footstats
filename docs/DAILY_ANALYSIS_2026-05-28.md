# FootStats Daily Analysis — 2026-05-28

## Co wykryto

### 🔴 CRITICAL: Rekurencyjna korupcja plików (3. raz!)
**12 plików** na dysku uszkodzonych — obcięte lub null bytes. Git HEAD OK.

**Truncated (8):** daily_agent.py (1381→1414), analyzer.py (1377→1393), poisson.py (241→267), backtest.py (583→589), superbet.py (1115→1128), base_playwright.py (307→317), superbet_bb.py (290→292), scrapers/__init__.py (18→?)

**Null bytes (4):** dashboard.py (466), ensemble_optimizer.py (119), probability_calibrator.py (99), post_match_analyzer.py (2)

**Przyczyna:** Prawdopodobnie edytor/narzędzie AI obcina pliki przy zapisie. To 3. raz od 05-26.

### 🟡 Bloat
- `gui/node_modules/` = **3.1GB** — NIE w .gitignore
- `cache/` = 283MB, `.aider.tags.cache.v4/` = 768K orphan

### 🟡 Stale files
- `CLAUDE_CODE_PROMPT_PHASE9.md`, `validation_errors.csv`, `.coverage`

### 🟡 Code quality
- ~233x `except Exception` (top: sts 13, cli 10, logging 8)
- 3 pliki >1000 LOC
- json_export.py — db.close() OK ale brak try/finally

### ✅ Co działa
- Git HEAD: wszystkie 12 plików OK
- SQLite context managers, HTTP timeouts, thread safety, operator agent, config v3.4

## Co poprawiono/zaproponowano

1. **STATUS.md** — zaktualizowany ze stanem BROKEN + poleceniem naprawczym
2. **TODO.md** — dodano Phase 10.0 (restore), 10.5 (cleanup), skonsolidowano 1-9

## Zalecane testy

1. `test_file_integrity_v2.py` — py_compile + null-byte check ALL .py
2. Pre-commit hook v2 z py_compile + null-byte check

## Claude Code Prompt

```
Tryb: caveman ultra. Bez wyjaśnień.

KROK 1 — RESTORE (BLOCKER):
git checkout HEAD -- src/footstats/daily_agent.py src/footstats/ai/analyzer.py src/footstats/ai/post_match_analyzer.py src/footstats/core/poisson.py src/footstats/core/backtest.py src/footstats/core/probability_calibrator.py src/footstats/core/ensemble_optimizer.py src/footstats/scrapers/superbet.py src/footstats/scrapers/base_playwright.py src/footstats/scrapers/superbet_bb.py src/footstats/scrapers/__init__.py src/footstats/dashboard.py

Verify: python -c "import py_compile,glob; errs=[f for f in glob.glob('src/**/*.py',recursive=True) if not py_compile.compile(f,doraise=False)]; print(f'{len(errs)} errors')"

KROK 2 — PRE-COMMIT HOOK:
cat > .git/hooks/pre-commit << 'HOOK'
#!/bin/bash
errors=0
for f in $(git diff --cached --name-only --diff-filter=ACM | grep '\.py$'); do
  python -m py_compile "$f" 2>/dev/null || { echo "SYNTAX ERROR: $f"; errors=1; }
  python -c "import sys; sys.exit(0 if b'\x00' not in open('$f','rb').read() else 1)" || { echo "NULL BYTES: $f"; errors=1; }
done
exit $errors
HOOK
chmod +x .git/hooks/pre-commit

KROK 3 — CLEANUP:
rm -f CLAUDE_CODE_PROMPT_PHASE9.md validation_errors.csv .coverage
rm -rf .aider.tags.cache.v4
echo "src/footstats/gui/node_modules/" >> .gitignore
sort -u -o .gitignore .gitignore
git add -A && git commit -m "[fix] restore 12 truncated files, cleanup stale, pre-commit hook v2"

KROK 4 — TEST:
cat > tests/test_file_integrity_v2.py << 'EOF'
import py_compile, glob, pathlib

def test_all_py_compile():
    errs = [f for f in glob.glob("src/**/*.py", recursive=True)
            if not py_compile.compile(f, doraise=False)]
    assert not errs, f"Syntax errors: {errs}"

def test_no_null_bytes():
    bad = [f for f in glob.glob("src/**/*.py", recursive=True)
           if b"\x00" in pathlib.Path(f).read_bytes()]
    assert not bad, f"Null bytes: {bad}"
EOF
pytest tests/test_file_integrity_v2.py -v
git add tests/test_file_integrity_v2.py && git commit -m "[test] file integrity gate"
```
