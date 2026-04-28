param(
  [Parameter(Mandatory = $true)]
  [string]$ProjectId,

  [string]$Region = "europe-west1",
  [string]$ServiceName = "chess-elo-coach-api",
  [string]$Model = "gemini-2.5-flash-lite"
)

$ErrorActionPreference = "Stop"

if (-not $env:CLOUDSDK_PYTHON) {
  foreach ($candidate in @("C:\Python314\python.exe", "C:\Python313\python.exe", "C:\Python312\python.exe", "C:\Python311\python.exe")) {
    if (Test-Path $candidate) {
      $env:CLOUDSDK_PYTHON = $candidate
      break
    }
  }
}

$gcloudCommand = Get-Command gcloud -ErrorAction SilentlyContinue
if ($gcloudCommand) {
  $gcloud = $gcloudCommand.Source
} else {
  $gcloud = "C:\ProgramData\chocolatey\lib\gcloudsdk\tools\google-cloud-sdk\bin\gcloud.ps1"
  if (-not (Test-Path $gcloud)) {
    throw "gcloud introuvable. Installe Google Cloud CLI ou ouvre un nouveau terminal."
  }
}

$apiKey = $env:GEMINI_API_KEY
if (-not $apiKey) {
  $secure = Read-Host "Colle ta GEMINI_API_KEY Google AI Studio" -AsSecureString
  $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
  try {
    $apiKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
  } finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
  }
}

if (-not $apiKey) {
  throw "GEMINI_API_KEY manquante."
}

& $gcloud config set project $ProjectId
if ($LASTEXITCODE -ne 0) { throw "Impossible de selectionner le projet $ProjectId." }

& $gcloud run services update $ServiceName `
  --project $ProjectId `
  --region $Region `
  --update-env-vars "AI_PROVIDER=auto,AI_RERANK_PROVIDER=gemini,AI_RERANK_TIMEOUT_SECONDS=2.5,GEMINI_MODEL=$Model,GEMINI_API_KEY=$apiKey"
if ($LASTEXITCODE -ne 0) { throw "Impossible de configurer Gemini sur Cloud Run." }

Write-Host "Gemini est configure sur $ServiceName avec le modele $Model."
