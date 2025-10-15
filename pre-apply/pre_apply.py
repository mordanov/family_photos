#!/usr/bin/env python3
import argparse
import base64
import random
import string
import sys
import os
import time
import hashlib
import json
import requests
import boto3
from botocore.exceptions import ClientError
from nacl import encoding, public

# ==== Default Configuration ====
IAM_USERNAME = "family_user"
AWS_REGION = "us-east-1"
GH_TOKEN = os.environ.get("GH_SECRET_TOKEN", "")
GITHUB_OWNER = "mordanov"
REPOSITORY_NAME = "family_photos"
AWS_PROFILE = "default"
PRE_APPLY_SCRIPT = "./aws/pre_apply.yaml"

# ==== GitHub API Functions ====
def get_github_repo_public_key():
    print("Fetching GitHub repository public key...")
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{REPOSITORY_NAME}/actions/secrets/public-key"

    retries = 3
    for i in range(1, retries + 1):
        response = requests.get(
            url,
            headers={
                "Authorization": f"Bearer {GH_TOKEN}",
                "Accept": "application/vnd.github.v3+json"
            }
        )
        if response.status_code == 200:
            data = response.json()
            if data.get("key") and data.get("key_id"):
                print("Public key and key ID successfully retrieved.")
                return data["key"], data["key_id"]
        print(f"Failed to fetch public key (attempt {i}/{retries}).")
        time.sleep(5)

    sys.exit(f"Error: Could not retrieve GitHub public key after {retries} attempts: {response.text}")


def encrypt_secret(secret_value, public_key_b64):
    pk = public.PublicKey(public_key_b64, encoding.Base64Encoder())
    sealed_box = public.SealedBox(pk)
    encrypted = sealed_box.encrypt(secret_value.encode("utf-8"))
    return base64.b64encode(encrypted).decode("utf-8")


def push_github_secret(secret_name, secret_value, key_id, public_key_b64):
    retries = 3
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{REPOSITORY_NAME}/actions/secrets/{secret_name}"

    for i in range(1, retries + 1):
        encrypted_value = encrypt_secret(secret_value, public_key_b64)
        payload = {"key_id": key_id, "encrypted_value": encrypted_value}

        response = requests.put(
            url,
            headers={
                "Authorization": f"Bearer {GH_TOKEN}",
                "Accept": "application/vnd.github.v3+json"
            },
            json=payload
        )

        if response.status_code in (201, 204):
            print(f"✅ Secret {secret_name} successfully pushed to GitHub")
            return

        print(f"⚠️ Failed to push secret {secret_name} (attempt {i}/{retries}). Status: {response.status_code}")
        time.sleep(5)

    sys.exit(f"❌ Failed to push secret {secret_name} after {retries} attempts: {response.text}")

# ==== AWS Functions ====
def md5_hash(text):
    return hashlib.md5(text.encode("utf-8")).hexdigest()

def stack_exists(cf_client, stack_name):
    try:
        cf_client.describe_stacks(StackName=stack_name)
        return True
    except ClientError as e:
        if "does not exist" in str(e):
            return False
        else:
            raise

def deploy_cloudformation(script_path):
    print(f"Deploying CloudFormation script from '{script_path}'...")
    if not os.path.isfile(script_path):
        sys.exit(f"❌ Error: CloudFormation script '{script_path}' not found")

    with open(script_path) as f:
        template_body = f.read()

    template_hash = md5_hash(template_body)

    session = boto3.Session(profile_name=AWS_PROFILE, region_name=AWS_REGION)
    cf = session.client("cloudformation")
    stack_name = "pre-apply-stack"

    if stack_exists(cf, stack_name):
        print("ℹ️ Stack exists, checking if update is needed...")
        try:
            current_template = cf.get_template(StackName=stack_name)["TemplateBody"]
            current_hash = md5_hash(json.dumps(current_template))
        except Exception:
            current_hash = None

        if current_hash == template_hash:
            print("✅ No changes detected in CloudFormation template — skipping update")
            return

        print("🔄 Changes detected — updating stack...")
        try:
            cf.update_stack(
                StackName=stack_name,
                TemplateBody=template_body,
                Capabilities=["CAPABILITY_IAM", "CAPABILITY_NAMED_IAM"]
            )
            waiter = cf.get_waiter("stack_update_complete")
            waiter.wait(StackName=stack_name)
            print("✅ CloudFormation stack updated successfully")
        except ClientError as e:
            if "No updates are to be performed" in str(e):
                print("✅ No changes to apply")
            else:
                raise
    else:
        print("🆕 Creating CloudFormation stack...")
        cf.create_stack(
            StackName=stack_name,
            TemplateBody=template_body,
            Capabilities=["CAPABILITY_IAM", "CAPABILITY_NAMED_IAM"]
        )
        waiter = cf.get_waiter("stack_create_complete")
        waiter.wait(StackName=stack_name)
        print("✅ CloudFormation stack created successfully")


def generate_aws_keys():
    print("🔑 Generating new AWS IAM access key...")
    session = boto3.Session(profile_name=AWS_PROFILE, region_name=AWS_REGION)
    iam = session.client("iam")

    keys = iam.list_access_keys(UserName=IAM_USERNAME)["AccessKeyMetadata"]
    if len(keys) >= 2:
        print("⚠️ Maximum number of access keys reached — deleting old keys...")
        for key in keys:
            iam.delete_access_key(UserName=IAM_USERNAME, AccessKeyId=key["AccessKeyId"])

    new_key = iam.create_access_key(UserName=IAM_USERNAME)["AccessKey"]
    print("✅ AWS IAM access key generated successfully")
    return new_key["AccessKeyId"], new_key["SecretAccessKey"]


def get_aws_account_id():
    session = boto3.Session(profile_name=AWS_PROFILE, region_name=AWS_REGION)
    return session.client("sts").get_caller_identity()["Account"]

def generate_pg_password(length=8):
    if length < 4:
        raise ValueError("Password length must be at least 4 to include all character types.")

    letters_upper = string.ascii_uppercase
    letters_lower = string.ascii_lowercase
    digits = '123456789'
    symbols = '!@#$%^&*()-+='

    # Ensure at least one character from each category
    password = [
        random.choice(letters_upper),
        random.choice(letters_lower),
        random.choice(digits),
        random.choice(symbols)
    ]

    # Fill the rest with random choices from all allowed characters
    all_chars = letters_upper + letters_lower + digits + symbols
    password += [random.choice(all_chars) for _ in range(length - 4)]

    random.shuffle(password)
    return ''.join(password)

# ==== Main ====
def main():
    parser = argparse.ArgumentParser(description="Deploy GitHub secrets and manage AWS resources.")
    parser.add_argument("--deploy-pre-apply", action="store_true")
    parser.add_argument("--generate-key", action="store_true")
    parser.add_argument("--update-secrets", action="store_true")
    parser.add_argument("--gh-token", type=str)
    parser.add_argument("--repo-owner", type=str)
    parser.add_argument("--repo-name", type=str)
    parser.add_argument("--profile", type=str)
    args = parser.parse_args()

    global GH_TOKEN, GITHUB_OWNER, REPOSITORY_NAME, AWS_PROFILE

    if args.gh_token:
        GH_TOKEN = args.gh_token
    if args.repo_owner:
        GITHUB_OWNER = args.repo_owner
    if args.repo_name:
        REPOSITORY_NAME = args.repo_name
    if args.profile:
        AWS_PROFILE = args.profile

    aws_access_key_id = None
    aws_secret_access_key = None

    if args.deploy_pre_apply:
        deploy_cloudformation(PRE_APPLY_SCRIPT)

    if args.generate_key:
        aws_access_key_id, aws_secret_access_key = generate_aws_keys()

    if args.update_secrets:
        if not GH_TOKEN:
            sys.exit("❌ Error: GitHub token is required (use --gh-token or export GH_SECRET_TOKEN)")

        if not aws_access_key_id or not aws_secret_access_key:
            sys.exit("❌ Error: AWS access keys required — generate keys first using --generate-key")

        public_key_b64, key_id = get_github_repo_public_key()
        aws_account_id = get_aws_account_id()

        pg_password = generate_pg_password()

        push_github_secret("AWS_ACCESS_KEY_ID", aws_access_key_id, key_id, public_key_b64)
        push_github_secret("AWS_SECRET_ACCESS_KEY", aws_secret_access_key, key_id, public_key_b64)
        push_github_secret("AWS_ACCOUNT_ID", aws_account_id, key_id, public_key_b64)
        push_github_secret("AWS_REGION", AWS_REGION, key_id, public_key_b64)
        push_github_secret("PG_USER", "pg_user", key_id, public_key_b64)
        push_github_secret("PG_PASSWORD", pg_password, key_id, public_key_b64)

        print(f"📕 Password for Postgres: `{pg_password}`")
        print("🎉 All secrets pushed to GitHub Actions successfully!")

    if not (args.deploy_pre_apply or args.generate_key or args.update_secrets):
        sys.exit("❌ Error: No action specified — use --deploy-pre-apply, --generate-key, or --update-secrets")


if __name__ == "__main__":
    main()