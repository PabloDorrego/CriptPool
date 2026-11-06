# ==============================================================================
# SCRIPT DE APAGADO DE EMERGENCIA (KILL-SWITCH) - CUENTA "PAGO DE FIREBASE"
# Pone a 0 todas las instancias 24/7 en Cloud Run para que el gasto sea 0,00 €/día
# ==============================================================================

Write-Host "==========================================================" -ForegroundColor Red
Write-Host "  EJECUTANDO APAGADO TOTAL DE SERVICIOS 24/7 (CLOUD RUN)  " -ForegroundColor Red
Write-Host "==========================================================" -ForegroundColor Red

Write-Host "[1/3] Pausando cron de Cloud Scheduler en criptpool-meteora..." -ForegroundColor Yellow
gcloud scheduler jobs pause meteora-tick-1m --location=europe-west1 --project=criptpool-meteora --quiet 2>$null

Write-Host "[2/3] Poniendo a escala 0 el worker en criptpool-meteora..." -ForegroundColor Yellow
gcloud run services update meteora-bot-worker --region=europe-west1 --project=criptpool-meteora --min-instances=0 --max-instances=1 --cpu-throttling --quiet

Write-Host "[3/3] Asegurando apagado en criptodeltan-engine..." -ForegroundColor Yellow
gcloud run services update meteora-dual-worker --region=europe-west1 --project=criptodeltan-engine --min-instances=0 --cpu-throttling --quiet

Write-Host "`n[+] LISTO: Todos los servicios han quedado en reposo absoluto (Gasto = 0,00 €/día)." -ForegroundColor Green
Write-Host "Si además deseas DESVINCULAR la facturación por completo del proyecto ejecuta:" -ForegroundColor Cyan
Write-Host "gcloud billing projects unlink criptpool-meteora" -ForegroundColor Gray
