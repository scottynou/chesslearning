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

if (-not $env:CLOUDSDK_PYTHON) {
  $pythonCandidates = @(
    "$root\backend\.venv\Scripts\python.exe",
    "C:\Python314\python.exe",
    "C:\Python313\python.exe",
    "C:\Python312\python.exe",
    "C:\Python311\python.exe"
  )
  $python = $pythonCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
  if ($python) {
    $env:CLOUDSDK_PYTHON = $python
  }
}

$gcloudCommand = Get-Command gcloud -ErrorAction SilentlyContinue
if ($gcloudCommand) {
  $gcloud = $gcloudCommand.Source
} else {
  $gcloud = "C:\ProgramData\chocolatey\lib\gcloudsdk\tools\google-cloud-sdk\bin\gcloud.cmd"
  if (-not (Test-Path $gcloud)) {
    throw "gcloud introuvable. Installe Google Cloud CLI ou ouvre un nouveau terminal."
  }
}

function Invoke-Gcloud {
  & $gcloud @args
  if ($LASTEXITCODE -ne 0) {
    throw "gcloud failed: $($args -join ' ')"
  }
}

Write-Host "Using Google Cloud project $ProjectId"
Invoke-Gcloud config set project $ProjectId

Write-Host "Enabling required APIs..."
Invoke-Gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com

$corsRegex = "https?://(localhost|127\.0\.0\.1)(:\d+)?|https://.*\.(onrender\.com|web\.app|firebaseapp\.com)"
$envVars = "AI_PROVIDER=heuristic,STOCKFISH_PATH=/usr/games/stockfish,FRONTEND_ORIGIN_REGEX=$corsRegex,RATE_LIMIT_WINDOW_SECONDS=60,RATE_LIMIT_PER_WINDOW=45"

Write-Host "Deploying $ServiceName to Cloud Run in $Region..."
Invoke-Gcloud run deploy $ServiceName `
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
Invoke-Gcloud run services describe $ServiceName --region $Region --format "value(status.url)"
