# Cloud migration — pełny pipeline PC-off (Cloud Run Jobs)

**Cel:** przenieść `daily_agent --faza final` (11:00) + `evening_agent` (23:00) z lokalnego
Windows Task Scheduler do chmury → PC może być wyłączony nocą. System draft (07:30 CEST)
i settlement już są cloudowe; to domyka migrację.

**Decyzja:** Cloud Run Jobs (nie request-bound jak /cron/draft; Playwright+Groq OK), nie Raspberry Pi
(infra GCP + Neon już stoi; Pi = port ARM + dubel). Koszt ~$0-5/mc (2 krótkie runy/dzień).

> ⚠️ Wymaga `gcloud` (Twoje konto/koszt). Poniżej gotowe komendy — uruchom jutro. Placeholdery `<...>` uzupełnij.

## 0. Zmienne
```bash
PROJECT=<gcp-project-id>
REGION=europe-west1
REPO=footstats            # Artifact Registry repo (utwórz jeśli brak)
IMAGE=$REGION-docker.pkg.dev/$PROJECT/$REPO/footstats-jobs:latest
```

## 1. Build + push obrazu jobs (Playwright)
```bash
gcloud builds submit --tag $IMAGE --dockerfile Dockerfile.jobs .
# lub lokalnie: docker build -f Dockerfile.jobs -t $IMAGE . && docker push $IMAGE
```

## 2. Sekrety (te same co lokalny .env)
Przez Cloud Run env lub Secret Manager. Minimum: `DATABASE_URL` (Neon), `GROQ_API_KEY`,
`BZZOIRO_KEY`, `TELEGRAM_*` (jeśli final wysyła), `JWT_SECRET`. Ustaw `--set-secrets` / `--set-env-vars`.

## 3. Cloud Run Jobs (final + evening)
```bash
# JOB final — daily_agent --faza final
gcloud run jobs create footstats-final \
  --image $IMAGE --region $REGION \
  --set-env-vars JOB_PHASE=final \
  --set-secrets DATABASE_URL=DATABASE_URL:latest,GROQ_API_KEY=GROQ_API_KEY:latest,BZZOIRO_KEY=BZZOIRO_KEY:latest \
  --memory 2Gi --cpu 2 --task-timeout 1200 --max-retries 1

# JOB evening — evening_agent
gcloud run jobs create footstats-evening \
  --image $IMAGE --region $REGION \
  --set-env-vars JOB_PHASE=evening \
  --set-secrets DATABASE_URL=DATABASE_URL:latest,GROQ_API_KEY=GROQ_API_KEY:latest,BZZOIRO_KEY=BZZOIRO_KEY:latest \
  --memory 2Gi --cpu 2 --task-timeout 1200 --max-retries 1
```
Playwright chromium potrzebuje ≥2Gi RAM. `--task-timeout 1200` = 20 min (scraping+Groq).

## 4. Cloud Scheduler → triggery (CEST = Europe/Warsaw)
```bash
SA=<scheduler-sa>@$PROJECT.iam.gserviceaccount.com   # z rolą run.invoker

gcloud scheduler jobs create http footstats-final-trigger \
  --location $REGION --schedule "0 11 * * *" --time-zone "Europe/Warsaw" \
  --uri "https://$REGION-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/$PROJECT/jobs/footstats-final:run" \
  --http-method POST --oauth-service-account-email $SA

gcloud scheduler jobs create http footstats-evening-trigger \
  --location $REGION --schedule "0 23 * * *" --time-zone "Europe/Warsaw" \
  --uri "https://$REGION-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/$PROJECT/jobs/footstats-evening:run" \
  --http-method POST --oauth-service-account-email $SA
```

## 5. Weryfikacja (przed wyłączeniem lokalnych)
```bash
gcloud run jobs execute footstats-final --region $REGION --wait
# sprawdź: kupony w Neon (created_at ~teraz), Telegram doszedł, logi bez błędu
```

## 6. Wyłącz lokalne taski (dopiero po potwierdzeniu parytetu)
PowerShell:
```powershell
Disable-ScheduledTask -TaskName "FootStats-DailyAgentFinal"
Disable-ScheduledTask -TaskName "FootStats-EveningAgent"
Disable-ScheduledTask -TaskName "FootStats-DailyAgentDraft"   # draft już w cloud (footstats-draft-morning)
```

## Rollback
`gcloud scheduler jobs pause footstats-final-trigger` + `Enable-ScheduledTask` lokalnie.

---
**Po migracji:** PC może być off. Zostają cloud: draft 07:30 + final 11:00 + evening 23:00 + settlement 06:00/21:30 UTC.
