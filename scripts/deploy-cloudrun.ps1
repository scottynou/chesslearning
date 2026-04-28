param(
  [Parameter(Mandatory = $true)]
  [string]$ProjectId,

  [string]$Region = "europe-west1",
  [string]$ServiceName = "chess-elo-coach-api",
  [int]$MinInstances = 1,
  [int]$MaxInstances = 3
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

Write-Host "Using Google Cloud project $ProjectId"
gcloud config set project $ProjectId

Write-Host "Enabling required APIs..."
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com

$corsRegex = "https?://(localhost|127\.0\.0\.1)(:\d+)?|https://.*\.(onrender\.com|web\.app|firebaseapp\.com)"
$envVars = "AI_PROVIDER=heuristic,STOCKFISH_PATH=/usr/games/stockfish,FRONTEND_ORIGIN_REGEX=$corsRegex,RATE_LIMIT_WINDOW_SECONDS=60,RATE_LIMIT_PER_WINDOW=45"

Write-Host "Deploying $ServiceName to Cloud Run in $Region..."
gcloud run deploy $ServiceName `
  --source "$root\backend" `
  --region $Region `
  --allow-unauthenticated `
  --min-instances $MinInstances `
  --max-instances $MaxInstances `
  --memory 1Gi `
  --cpu 1 `
  --concurrency 10 `
  --timeout 45 `
  --set-env-vars $envVars

Write-Host "Cloud Run URL:"
gcloud run services describe $ServiceName --region $Region --format "value(status.url)"
