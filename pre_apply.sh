#!/bin/bash

# ==== User Instructions ====
function usage() {
  echo "Usage: $0 [OPTIONS]"
  echo ""
  echo "A shell script to deploy GitHub secrets and manage AWS resources."
  echo ""
  echo "Options:"
  echo "  --deploy-pre-apply      Deploy the CloudFormation script before generating keys"
  echo "  --generate-key          Generate a new AWS IAM access key"
  echo "  --update-secrets        Update GitHub secrets"
  echo "  --gh-token TOKEN        GitHub personal access token (or export GH_SECRET_TOKEN)"
  echo "  --repo-owner OWNER      GitHub repository owner (default: mordanov)"
  echo "  --repo-name NAME        GitHub repository name (default: family_photos)"
  echo "  --profile PROFILE       AWS CLI profile to use (default: default)"
  echo "  --help                  Display this help message"
  exit 1
}

# ==== Default Configuration ====
IAM_USERNAME="family_user"               # IAM User name (default configuration)
AWS_REGION="us-east-1"                   # AWS Region (default configuration)
GH_TOKEN="${GH_SECRET_TOKEN:-}"          # GitHub personal access token (from env var)
GITHUB_OWNER="mordanov"                  # GitHub repo owner
REPOSITORY_NAME="family_photos"          # GitHub repo name
AWS_PROFILE="default"                    # AWS CLI profile

GENERATE_KEY=false                       # Initialize flag for AWS IAM access key generation
UPDATE_SECRETS=false                     # Initialize flag for GitHub secret updates
DEPLOY_PRE_APPLY=false                   # Initialize flag for CloudFormation deployment

PRE_APPLY_SCRIPT="./aws/pre_apply.yaml"  # Path to the CloudFormation script

# ==== Parse Command-Line Arguments ====
while [[ $# -gt 0 ]]; do
  case "$1" in
    --deploy-pre-apply)
      DEPLOY_PRE_APPLY=true
      shift
      ;;
    --generate-key)
      GENERATE_KEY=true
      shift
      ;;
    --update-secrets)
      UPDATE_SECRETS=true
      shift
      ;;
    --gh-token)
      GH_TOKEN="$2"
      shift 2
      ;;
    --repo-owner)
      GITHUB_OWNER="$2"
      shift 2
      ;;
    --repo-name)
      REPOSITORY_NAME="$2"
      shift 2
      ;;
    --profile)
      AWS_PROFILE="$2"
      shift 2
      ;;
    --help)
      usage
      ;;
    *)
      echo "Unknown option: $1"
      usage
      ;;
  esac
done

# ==== Validate Mandatory Variables ====
if [[ -z "$GH_TOKEN" ]]; then
  echo "Error: GitHub token is required. Use --gh-token or export GH_SECRET_TOKEN."
  exit 1
fi

# ==== Function to Deploy CloudFormation Script ====
deploy_cloudformation() {
  echo "Deploying CloudFormation script from '$PRE_APPLY_SCRIPT'..."
  if [[ ! -f "$PRE_APPLY_SCRIPT" ]]; then
    echo "Error: CloudFormation script '$PRE_APPLY_SCRIPT' not found."
    exit 1
  fi

  aws cloudformation deploy \
    --template-file "$PRE_APPLY_SCRIPT" \
    --stack-name pre-apply-stack \
    --region "$AWS_REGION" \
    --profile "$AWS_PROFILE" \
    --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM

  if [[ $? -ne 0 ]]; then
    echo "Error: Failed to deploy CloudFormation script."
    exit 1
  fi

  echo "CloudFormation script deployed successfully."
}

# ==== Function to Fetch GitHub Repository Public Key ====
get_github_repo_public_key() {
  echo "Fetching GitHub repository public key..."
  local API_URL="https://api.github.com/repos/${GITHUB_OWNER}/${REPOSITORY_NAME}/actions/secrets/public-key"

  local response=$(curl -s -H "Authorization: Bearer $GH_TOKEN" -H "Accept: application/vnd.github.v3+json" "$API_URL")

  PUBLIC_KEY=$(echo "$response" | jq -r '.key')
  KEY_ID=$(echo "$response" | jq -r '.key_id')

  if [[ -z "$PUBLIC_KEY" || -z "$KEY_ID" ]]; then
    echo "Error: Failed to retrieve GitHub repository public key. Response: $response"
    exit 1
  fi

  echo "Public key and key ID fetched successfully."
}

# ==== Function to Encrypt Secret ====
encrypt_secret() {
  local secret_value=$1

  # Decode the Base64 public key from GitHub and save it as a DER file
  echo "$PUBLIC_KEY" | base64 -d > /tmp/github_public_key.der

  # Convert the DER-formatted public key into PEM format
  openssl rsa -pubin -inform DER -in /tmp/github_public_key.der -out /tmp/github_public_key.pem 2>/dev/null

  # Ensure the PEM file exists and is valid
  if [[ ! -f /tmp/github_public_key.pem ]] || ! openssl pkey -pubin -in /tmp/github_public_key.pem -text >/dev/null 2>&1; then
    echo "Error: Invalid public key format or failed to decode public key."
    rm -f /tmp/github_public_key.der
    exit 1
  fi

  # Encrypt the secret using `pkeyutl` and output the result in Base64
  local encrypted_value=$(echo -n "$secret_value" | \
    openssl pkeyutl -encrypt -pubin -inkey /tmp/github_public_key.pem | \
    base64 -w0)

  # Clean up temporary files
  rm -f /tmp/github_public_key.der /tmp/github_public_key.pem

  if [[ -z "$encrypted_value" ]]; then
    echo "Error: Failed to encrypt secret value."
    exit 1
  fi

  echo "$encrypted_value"
}

# ==== Function to Push Secrets to GitHub ====
push_github_secret() {
  local secret_name=$1
  local secret_value=$2

  # Encrypt the secret value using the repository's public key
  local encrypted_value=$(encrypt_secret "$secret_value")

  # API URL for creating/updating GitHub Actions secrets
  local API_URL="https://api.github.com/repos/${GITHUB_OWNER}/${REPOSITORY_NAME}/actions/secrets/${secret_name}"

  # Send PUT request to GitHub API
  local response=$(curl -s -X PUT "$API_URL" \
    -H "Authorization: Bearer $GH_TOKEN" \
    -H "Content-Type: application/json" \
    -H "Accept: application/vnd.github.v3+json" \
    -d "$(jq -n --arg key_id "$KEY_ID" --arg encrypted_value "$encrypted_value" '{"key_id": $key_id, "encrypted_value": $encrypted_value}')")

  if [[ $(echo "$response" | jq -r '.message') == "null" ]]; then
    echo "Secret $secret_name successfully pushed to GitHub."
  else
    echo "Error pushing secret $secret_name. Response: $response"
  fi
}

# ==== Deploy CloudFormation Script ====
if $DEPLOY_PRE_APPLY; then
  deploy_cloudformation
fi

# ==== Generate AWS IAM Access Keys ====
if $GENERATE_KEY; then
  echo "Generating new AWS IAM access key..."
  IAM_KEYS=$(aws iam create-access-key --user-name "$IAM_USERNAME" --region "$AWS_REGION" --profile "$AWS_PROFILE")

  if [[ $? -ne 0 ]]; then
    echo "Error: Failed to create AWS IAM access key using profile '$AWS_PROFILE'."
    exit 1
  fi

  AWS_ACCESS_KEY_ID=$(echo "$IAM_KEYS" | jq -r '.AccessKey.AccessKeyId')
  AWS_SECRET_ACCESS_KEY=$(echo "$IAM_KEYS" | jq -r '.AccessKey.SecretAccessKey')

  echo "AWS IAM access key generated successfully."
fi

# ==== Update GitHub Secrets ====
if $UPDATE_SECRETS; then
  echo "Updating GitHub secrets..."

  if [[ -z "$AWS_ACCESS_KEY_ID" || -z "$AWS_SECRET_ACCESS_KEY" ]]; then
    echo "Error: AWS access keys are not generated or provided. Generate keys first using --generate-key."
    exit 1
  fi

  # Retrieve the AWS Account ID
  AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query "Account" --output text --profile "$AWS_PROFILE")

  # Push secrets to GitHub
  push_github_secret "AWS_ACCESS_KEY_ID" "$AWS_ACCESS_KEY_ID"
  push_github_secret "AWS_SECRET_ACCESS_KEY" "$AWS_SECRET_ACCESS_KEY"
  push_github_secret "AWS_ACCOUNT_ID" "$AWS_ACCOUNT_ID"
  push_github_secret "AWS_REGION" "$AWS_REGION"

  echo "Secrets successfully pushed to GitHub Actions!"
fi

if ! $GENERATE_KEY && ! $UPDATE_SECRETS && ! $DEPLOY_PRE_APPLY; then
  echo "Error: No action specified. Use --deploy-pre-apply, --generate-key, or --update-secrets."
  usage
fi