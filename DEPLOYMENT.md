


# ☁️ Google Cloud Deployment Guide

This guide details the exact commands used to provision the **Autonomic AI** infrastructure on Google Cloud Platform. It covers IAM permissions, Secret Manager, Pub/Sub topics, and Cloud Run deployment.

## 1. Project Initialization
Set your project ID and environment variables.

```bash
# Set your project ID
export PROJECT_ID="your-project-id-here"
export REGION="us-central1"

gcloud config set project $PROJECT_ID

```

## 2. Secret Management

We use Google Secret Manager to securely store the Datadog API Key.

```bash
# Create the secret for Datadog
echo -n "YOUR_ACTUAL_DATADOG_API_KEY" | gcloud secrets create DD_API_KEY --data-file=-

# Retrieve Project Number for IAM binding
export PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format="value(projectNumber)")

# Grant "Secret Accessor" to Cloud Build so it can inject secrets during build/deploy
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$PROJECT_NUMBER@cloudbuild.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor"

# Grant "Secret Accessor" to the Compute Engine default service account (Runtime)
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$PROJECT_NUMBER-compute@developer.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor"

```

## 3. IAM & Permissions

Granting necessary roles for Cloud Run and Cloud Build.

```bash
# Grant Cloud Run Admin role to Cloud Build
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$PROJECT_NUMBER@cloudbuild.gserviceaccount.com" \
    --role="roles/run.admin"

# Grant Service Account User to allow Cloud Build to act as the runtime service account
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$PROJECT_NUMBER@cloudbuild.gserviceaccount.com" \
    --role="roles/iam.serviceAccountUser"

```

## 4. Infrastructure Components

### Enable Services & Artifact Registry

```bash
gcloud services enable firestore.googleapis.com run.googleapis.com artifactregistry.googleapis.com

gcloud artifacts repositories create autonomic-repo \
    --repository-format=docker \
    --location=$REGION \
    --description="Docker repo for Autonomic AI"

```

### Pub/Sub Topics (The Nervous System)

We create distinct topics for the event-driven architecture.

```bash
# Create Topics
gcloud pubsub topics create autonomic-audit-jobs
gcloud pubsub topics create autonomic-refine-jobs
gcloud pubsub topics create autonomic-eval-jobs

# Create Subscriptions
# Auditor listens to Audit Jobs (from Gateway)
gcloud pubsub subscriptions create sub-auditor --topic=autonomic-audit-jobs

# Refiner listens to Refine Jobs (from Auditor or Evaluator)
gcloud pubsub subscriptions create sub-refiner --topic=autonomic-refine-jobs

# Evaluator listens to Eval Jobs (from Refiner)
gcloud pubsub subscriptions create sub-evaluator --topic=autonomic-eval-jobs

```

## 5. Deployment

Deploy the services using Cloud Build.

```bash
# Submit the build
gcloud builds submit --config cloudbuild.yaml .

# OR manually trigger with a substitution
gcloud builds submit --config cloudbuild.yaml --substitutions=SHORT_SHA=manual-v1 .

```

## 6. Public Access (Gateway Only)

Finally, expose the Gateway service to the internet while keeping backend agents internal/private.

```bash
gcloud run services add-iam-policy-binding autonomic-gateway \
    --region=$REGION \
    --member=allUsers \
    --role=roles/run.invoker

```



---





