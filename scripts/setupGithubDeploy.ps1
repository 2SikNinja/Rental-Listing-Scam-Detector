# =====================================================================
# setupGithubDeploy.ps1
#
# One-time Google Cloud setup so GitHub Actions can deploy the API to
# Cloud Run WITHOUT any stored keys (Workload Identity Federation).
#
# How it works:
#   1. GitHub gives each workflow run a signed identity token that says
#      which repo and branch it is running for.
#   2. Google checks that token against the rules created here, and only
#      trusts runs from this repo's master branch.
#   3. Google returns a short-lived credential (about 1 hour) for a
#      deploy-only service account. Nothing long-lived is ever stored.
#
# Run from the repo root, after `gcloud init`:
#   powershell -ExecutionPolicy Bypass -File .\scripts\setupGithubDeploy.ps1
#
# Safe to re-run: every step checks whether it already exists.
# =====================================================================

param(
    [string]$region = "us-west1",
    [string]$githubRepo = "2SikNinja/Rental-Listing-Scam-Detector",
    [string]$deployBranch = "master"
)

# "Continue", not "Stop": gcloud writes normal progress and expected
# "not found" messages to stderr, and Windows PowerShell 5.1 turns any
# stderr text into a fatal error under "Stop". Success or failure is
# decided by each command's exit code ($LASTEXITCODE) instead.
$ErrorActionPreference = "Continue"

function Test-GcloudResource {
    param([scriptblock]$describeCommand)
    & $describeCommand 2>&1 | Out-Null
    return ($LASTEXITCODE -eq 0)
}

function Invoke-Gcloud {
    param([string]$stepName, [scriptblock]$command)
    Write-Host "==> $stepName" -ForegroundColor Cyan
    # Capture everything gcloud prints and only show it if the step fails,
    # so normal progress messages don't look like errors.
    $commandOutput = & $command 2>&1
    if ($LASTEXITCODE -ne 0) {
        $commandOutput | ForEach-Object { Write-Host $_ -ForegroundColor Red }
        throw "Failed: $stepName"
    }
}

$projectId = (gcloud config get-value project 2>$null).Trim()
if (-not $projectId) { throw "No project selected. Run: gcloud init" }
$projectNumber = (gcloud projects describe $projectId --format "value(projectNumber)").Trim()

$poolId = "github"
$providerId = "github-actions"
$deployerEmail = "github-deployer@$projectId.iam.gserviceaccount.com"
$runtimeEmail = "rental-scam-api@$projectId.iam.gserviceaccount.com"
$registryRepo = "cloud-run-source-deploy"
$providerName = "projects/$projectNumber/locations/global/workloadIdentityPools/$poolId/providers/$providerId"
$githubPrincipal = "principalSet://iam.googleapis.com/projects/$projectNumber/locations/global/workloadIdentityPools/$poolId/attribute.repository/$githubRepo"

Write-Host "Project: $projectId ($projectNumber)" -ForegroundColor Green

Invoke-Gcloud "Enabling identity APIs" {
    gcloud services enable iamcredentials.googleapis.com sts.googleapis.com artifactregistry.googleapis.com
}

# ---------------------------------------------------------------------
# 1. Workload identity pool and GitHub provider
# ---------------------------------------------------------------------
if (Test-GcloudResource { gcloud iam workload-identity-pools describe $poolId --location global }) {
    Write-Host "==> Identity pool exists, skipping"
} else {
    Invoke-Gcloud "Creating identity pool" {
        gcloud iam workload-identity-pools create $poolId --location global --display-name "GitHub Actions"
    }
}

# Only tokens from this exact repo AND branch are accepted. A pull request
# branch or a fork cannot deploy, even if someone copies the workflow.
$attributeCondition = "assertion.repository=='$githubRepo' && assertion.ref=='refs/heads/$deployBranch'"

if (Test-GcloudResource { gcloud iam workload-identity-pools providers describe $providerId --location global --workload-identity-pool $poolId }) {
    Write-Host "==> GitHub provider exists, skipping"
} else {
    Invoke-Gcloud "Creating GitHub provider (trusts only $githubRepo on $deployBranch)" {
        gcloud iam workload-identity-pools providers create-oidc $providerId `
            --location global `
            --workload-identity-pool $poolId `
            --display-name "GitHub repo" `
            --issuer-uri "https://token.actions.githubusercontent.com" `
            --attribute-mapping "google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref" `
            --attribute-condition "$attributeCondition"
    }
}

# ---------------------------------------------------------------------
# 2. Deploy-only service account (least privilege)
# ---------------------------------------------------------------------
if (Test-GcloudResource { gcloud iam service-accounts describe $deployerEmail }) {
    Write-Host "==> Deployer service account exists, skipping"
} else {
    Invoke-Gcloud "Creating deployer service account" {
        gcloud iam service-accounts create github-deployer --display-name "GitHub Actions deployer"
    }
}

if (-not (Test-GcloudResource { gcloud artifacts repositories describe $registryRepo --location $region })) {
    Invoke-Gcloud "Creating image registry" {
        gcloud artifacts repositories create $registryRepo --repository-format docker --location $region
    }
}

Invoke-Gcloud "Allowing deployer to push images (this registry only)" {
    gcloud artifacts repositories add-iam-policy-binding $registryRepo --location $region `
        --member "serviceAccount:$deployerEmail" --role roles/artifactregistry.writer --quiet
}

Invoke-Gcloud "Allowing deployer to release new Cloud Run revisions" {
    gcloud projects add-iam-policy-binding $projectId `
        --member "serviceAccount:$deployerEmail" --role roles/run.developer --condition None --quiet
}

Invoke-Gcloud "Allowing deployer to run the service as its existing identity" {
    gcloud iam service-accounts add-iam-policy-binding $runtimeEmail `
        --member "serviceAccount:$deployerEmail" --role roles/iam.serviceAccountUser --quiet
}

Invoke-Gcloud "Allowing GitHub ($githubRepo) to act as the deployer" {
    gcloud iam service-accounts add-iam-policy-binding $deployerEmail `
        --member "$githubPrincipal" --role roles/iam.workloadIdentityUser --quiet
}

# ---------------------------------------------------------------------
# Output: values to save as GitHub repository variables (not secrets;
# none of these grant access on their own)
# ---------------------------------------------------------------------
Write-Host ""
Write-Host "Setup complete. Add these as GitHub repository VARIABLES:" -ForegroundColor Green
Write-Host "  GCP_PROJECT_ID   = $projectId"
Write-Host "  GCP_WIF_PROVIDER = $providerName"
Write-Host "  GCP_DEPLOY_SA    = $deployerEmail"
