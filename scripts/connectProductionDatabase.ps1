# =====================================================================
# connectProductionDatabase.ps1
#
# Connects the Cloud Run API to the Supabase database, safely:
#   1. Generates a strong random password for the locked-down scam_api
#      database role (it never appears on screen).
#   2. Has you set that password in Supabase's SQL editor (clipboard).
#   3. Tests the connection BEFORE changing production.
#   4. Stores the connection string in Google Secret Manager.
#   5. Lets only the API's service account read that secret.
#   6. Points Cloud Run at the secret and turns saving on.
#
# Run from the repo root:
#   powershell -ExecutionPolicy Bypass -File .\scripts\connectProductionDatabase.ps1
# Safe to re-run: it rotates to a new password each time.
# =====================================================================

param(
    [string]$region = "us-west1",
    [string]$serviceName = "rental-scam-api",
    [string]$supabaseRef = "homjrrwvqyhdgguakbnn",
    [string]$secretName = "database-url"
)

$ErrorActionPreference = "Continue"

function Invoke-Step {
    param([string]$stepName, [scriptblock]$command)
    Write-Host "==> $stepName" -ForegroundColor Cyan
    $commandOutput = & $command 2>&1
    if ($LASTEXITCODE -ne 0) {
        $commandOutput | ForEach-Object { Write-Host $_ -ForegroundColor Red }
        throw "Failed: $stepName"
    }
}

$repoRoot = Split-Path $PSScriptRoot -Parent
$projectId = (gcloud config get-value project 2>$null).Trim()
$runtimeAccount = "$serviceName@$projectId.iam.gserviceaccount.com"

# ---------------------------------------------------------------------
# 1. Strong random password, kept in memory only
# ---------------------------------------------------------------------
$randomBytes = New-Object byte[] 32
[System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($randomBytes)
# URL-safe characters only, so it can go straight into a connection string
$dbPassword = [Convert]::ToBase64String($randomBytes).Replace("+", "-").Replace("/", "_").TrimEnd("=")

# ---------------------------------------------------------------------
# 2. Set the password in Supabase
# ---------------------------------------------------------------------
Set-Clipboard -Value "alter role scam_api with login password '$dbPassword';"
Write-Host ""
Write-Host "STEP A: A SQL command is now on your clipboard." -ForegroundColor Yellow
Write-Host "  1. Open https://supabase.com/dashboard/project/$supabaseRef/sql/new"
Write-Host "  2. Paste (Ctrl+V) and click Run. You should see 'Success. No rows returned.'"
Write-Host "  3. Don't save the query as a snippet."
Read-Host "Press Enter here once it has run"
Set-Clipboard -Value " "  # clear the password from the clipboard

# ---------------------------------------------------------------------
# 3. Pooler host, then test the connection before touching production
# ---------------------------------------------------------------------
Write-Host ""
Write-Host "STEP B: In Supabase, click 'Connect' (top of the dashboard), choose 'Session pooler'," -ForegroundColor Yellow
Write-Host "  and copy just the host from the connection string, e.g. aws-0-us-west-1.pooler.supabase.com"
$poolerHost = (Read-Host "Paste the pooler host").Trim()
if ($poolerHost -notmatch '^[a-z0-9.-]+\.pooler\.supabase\.com$') {
    throw "That doesn't look like a Supabase pooler host (it should end in .pooler.supabase.com)."
}

# Cloud Run only has IPv4, so it connects through Supabase's pooler.
# The username includes the project ref so the pooler knows which database.
$databaseUrl = "postgresql://scam_api.${supabaseRef}:${dbPassword}@${poolerHost}:5432/postgres?sslmode=require"

Write-Host "==> Testing the connection as scam_api" -ForegroundColor Cyan
$env:CHECK_DATABASE_URL = $databaseUrl
Push-Location (Join-Path $repoRoot "apps\api")
$testOutput = uv run python -c "import os, psycopg; c = psycopg.connect(os.environ['CHECK_DATABASE_URL'], prepare_threshold=None, connect_timeout=10); print('Connected as', c.execute('select current_user').fetchone()[0])" 2>&1
$testExitCode = $LASTEXITCODE
Pop-Location
Remove-Item Env:CHECK_DATABASE_URL
if ($testExitCode -ne 0) {
    $testOutput | Where-Object { $_ -notmatch "UV_" } | ForEach-Object { Write-Host $_ -ForegroundColor Red }
    throw "Could not connect. Check that the SQL ran successfully and the host is right. Production was not changed."
}
Write-Host ($testOutput | Select-String "Connected as") -ForegroundColor Green

# ---------------------------------------------------------------------
# 4. Store the connection string in Secret Manager
# ---------------------------------------------------------------------
$tempFile = [System.IO.Path]::GetTempFileName()
try {
    [System.IO.File]::WriteAllText($tempFile, $databaseUrl)  # no trailing newline
    gcloud secrets describe $secretName 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Invoke-Step "Adding a new version of the $secretName secret" {
            gcloud secrets versions add $secretName --data-file $tempFile
        }
    } else {
        Invoke-Step "Creating the $secretName secret" {
            gcloud secrets create $secretName --data-file $tempFile
        }
    }
} finally {
    Remove-Item $tempFile -ErrorAction SilentlyContinue
}

# ---------------------------------------------------------------------
# 5. Only the API's own service account may read it
# ---------------------------------------------------------------------
Invoke-Step "Allowing the API (and only the API) to read the secret" {
    gcloud secrets add-iam-policy-binding $secretName `
        --member "serviceAccount:$runtimeAccount" --role roles/secretmanager.secretAccessor --quiet
}

# ---------------------------------------------------------------------
# 6. Point Cloud Run at the secret and turn saving on
# ---------------------------------------------------------------------
Invoke-Step "Updating Cloud Run (replaces the placeholder DATABASE_URL)" {
    gcloud run services update $serviceName --region $region `
        --remove-env-vars DATABASE_URL `
        --update-secrets "DATABASE_URL=${secretName}:latest" `
        --update-env-vars "PERSISTENCE_ENABLED=true,SUPABASE_URL=https://$supabaseRef.supabase.co"
}

$dbPassword = $null
$databaseUrl = $null
Write-Host ""
Write-Host "Done. The API now saves analyses to Supabase." -ForegroundColor Green
