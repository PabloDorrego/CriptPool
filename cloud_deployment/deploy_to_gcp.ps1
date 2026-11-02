# PowerShell Deployment Automation Script for CriptPool GCP + Firebase

$PROJECT_ID = "criptpool-meteora"
$REGION = "europe-west1"
$SERVICE_NAME = "meteora-bot-worker"

Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host "   DESPLIEGUE EN LA NUBE GCP: BOT METEORA DLMM + DASHBOARD WEB FIRESTORE       " -ForegroundColor Cyan
Write-Host "================================================================================" -ForegroundColor Cyan

# 1. Configurar Proyecto Activo
Write-Host "`n[*] 1. Configurando proyecto GCP activo: $PROJECT_ID..." -ForegroundColor Yellow
gcloud config set project $PROJECT_ID

# 2. Habilitar APIs necesarias
Write-Host "`n[*] 2. Habilitando APIs requeridas en Google Cloud..." -ForegroundColor Yellow
gcloud services enable firestore.googleapis.com run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com

# 3. Verificar o Crear Base de Datos Firestore (Modo Nativo)
Write-Host "`n[*] 3. Verificando base de datos Firestore..." -ForegroundColor Yellow
$dbs = gcloud firestore databases list --format="value(name)" 2>$null
if (-not $dbs) {
    Write-Host "  [+] Creando base de datos Firestore (Modo Nativo) en la región $REGION..." -ForegroundColor Green
    gcloud firestore databases create --location=$REGION --type=firestore-native
} else {
    Write-Host "  [+] Base de datos Firestore ya existente." -ForegroundColor Green
}

# 4. Desplegar Bot Worker en Cloud Run (Instancia continua 24/7)
Write-Host "`n[*] 4. Compilando y desplegando el Bot Worker en Google Cloud Run..." -ForegroundColor Yellow
$workerPath = Join-Path $PSScriptRoot "bot_worker"

gcloud run deploy $SERVICE_NAME `
    --source $workerPath `
    --region $REGION `
    --platform managed `
    --allow-unauthenticated `
    --min-instances 1 `
    --max-instances 1 `
    --memory 512Mi `
    --cpu 1 `
    --set-env-vars "GCP_PROJECT=$PROJECT_ID,POOL_ADDRESS=5rCf1DM8LjKTw4YqhnoLcngyZYeNnQqztScTogYHAS6,INITIAL_CAPITAL=10000.0,HALF_RANGE_PCT=0.075,POLL_INTERVAL_SEC=30"

Write-Host "`n[+] Bot Worker desplegado y corriendo 24/7 en Cloud Run." -ForegroundColor Green

# 5. Despliegue de la Web en Firebase Hosting
Write-Host "`n[*] 5. Desplegando Dashboard Web en Firebase Hosting..." -ForegroundColor Yellow
$webPath = Join-Path $PSScriptRoot "web_dashboard"
Set-Location $webPath

if (Get-Command firebase -ErrorAction SilentlyContinue) {
    firebase deploy --only hosting:criptopool-meteora,firestore:rules --project $PROJECT_ID
    Write-Host "`n[+] Dashboard Web publicado exitosamente en: https://criptopool-meteora.web.app" -ForegroundColor Green
} else {
    Write-Host "`n[!] Para desplegar la web independiente ejecuta:" -ForegroundColor Yellow
    Write-Host "    npx -y firebase-tools deploy --only hosting:criptopool-meteora --project $PROJECT_ID" -ForegroundColor White
}

Write-Host "`n================================================================================" -ForegroundColor Cyan
Write-Host "   SISTEMA DE MONITORIZACIÓN DE 30 DÍAS CONFIGURADO CON ÉXITO                  " -ForegroundColor Cyan
Write-Host "================================================================================" -ForegroundColor Cyan
