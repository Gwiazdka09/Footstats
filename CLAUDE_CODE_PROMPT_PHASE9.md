# Claude Code Prompt — Phase 9: DB Consolidation

Tryb: caveman ultra. Bez wyjasnien, czyste zmiany.

## TASK 1: Redeploy login fix (KRYTYCZNE)
Plik `src/footstats/db/migrations.py` seed_admin_user() juz naprawiony:
- SQL teraz ZAWSZE nadpisuje hash (usuniety WHERE password_hash='changeme')
- Commit + push + Cloud Run redeploy

```bash
git add src/footstats/db/migrations.py
git commit -m "[fix] seed_admin_user always updates hash from env var"
git push
# Cloud Run auto-deploy lub manual trigger
```

## TASK 2: Usun footstats.db
```bash
rm data/footstats.db
echo "data/footstats.db" >> .gitignore
```
Wyczyscic referencje:
- `scripts/czysc_baze.py` — usunac MAIN_DB = "footstats.db", zastapic BACKTEST_DB
- `scripts/backup_db.py:19` — usunac Path("data/footstats.db") z listy

```bash
git add -A && git commit -m "[cleanup] remove stale footstats.db, keep only backtest.db"
```

## TASK 3: Konsolidacja cache
```bash
# Przenies flashscore z src/cache/ do cache/
mv src/cache/flashscore cache/flashscore
rmdir src/cache 2>/dev/null

# Przenies .cache/ do cache/api_football/
mv .cache/af_budget.json cache/api_football/
mv .cache/af_cache.json cache/api_football/
rmdir .cache 2>/dev/null
```
Zaktualizuj importy:
- `scrapers/api_football.py` — zmien sciezke cache z `.cache/` na `cache/api_football/`
- `scrapers/flashscore_match.py` — zmien sciezke z `src/cache/flashscore/` na `cache/flashscore/`
- Grep: `grep -rn "\.cache\|src/cache" src/ --include="*.py"` i napraw

```bash
git add -A && git commit -m "[cleanup] consolidate cache dirs into cache/"
```

## TASK 4: ai/client.py timeout fix
W `src/footstats/ai/client.py` zmieniony timeout 120→15 moze byc za krotki dla Ollama.
Zmien na timeout=60 (kompromis).

```bash
git add src/footstats/ai/client.py
git commit -m "[fix] ai/client timeout 15→60 for LLM inference"
```

Po kazdym TASK: verify syntax `python -c "import py_compile; py_compile.compile('PLIK', doraise=True)"`
