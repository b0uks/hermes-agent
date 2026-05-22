---
name: cloud-cli
description: "Cloud provider CLI workflows for AWS and Google Cloud from Hermes Docker."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos]
prerequisites:
  commands: [aws, gcloud]
metadata:
  hermes:
    tags: [AWS, GCP, gcloud, Cloud, DevOps, CLI]
    category: devops
---

# Cloud CLI

Use `aws` and `gcloud` directly for cloud inspection and operations. Prefer read-only commands first, then make mutations only after the user confirms the target account/project/region.

## Docker Persistence

In the Hermes Docker image, CLI config is kept inside the persistent data volume:

```bash
HOME=/opt/data/home
AWS_CONFIG_FILE=$HOME/.config/aws/config
AWS_SHARED_CREDENTIALS_FILE=$HOME/.config/aws/credentials
CLOUDSDK_CONFIG=$HOME/.config/gcloud
```

This keeps auth/config across container restarts without mounting host dot-directories.

## First Checks

```bash
aws --version
aws sts get-caller-identity

gcloud version
gcloud auth list
gcloud config list
```

If auth is missing, ask which auth mode they want. Common options:

```bash
aws configure sso
aws configure

gcloud auth login --no-launch-browser
gcloud auth application-default login --no-launch-browser
gcloud auth activate-service-account --key-file /path/to/key.json
```

## AWS Patterns

Always identify the caller and region before changes:

```bash
aws sts get-caller-identity
aws configure list
aws configure get region
```

Useful read-only commands:

```bash
aws ec2 describe-instances --output table
aws s3 ls
aws logs describe-log-groups --output table
aws cloudformation list-stacks --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE --output table
```

Use `--profile` and `--region` explicitly when ambiguity matters:

```bash
aws --profile prod --region us-west-2 sts get-caller-identity
```

## Google Cloud Patterns

Always identify the account and project before changes:

```bash
gcloud auth list
gcloud config get-value project
gcloud config get-value compute/region
gcloud config get-value compute/zone
```

Useful read-only commands:

```bash
gcloud projects list
gcloud compute instances list
gcloud run services list --region REGION
gcloud logging logs list
```

Use `--project`, `--region`, and `--zone` explicitly when ambiguity matters:

```bash
gcloud compute instances list --project PROJECT_ID --zones us-central1-a
```

## Agent Rules

- Confirm identity/account/project before destructive or cost-incurring operations.
- Prefer `--format=json` for parsing and `--format=table(...)` for human summaries.
- Do not print credentials, tokens, or service account JSON.
- Keep commands narrow; cloud list operations can produce huge output.
