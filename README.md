# Family Photos project


## Pre-apply configuration

**TL;DR**

Before staring any deployments, it is mandatory to run pre-apply script.

This script creates initial infrastructure (that is not required to be changed when updating the code):
- AWS group, user
- Policy for providing access to Github actions into AWS infrastructure
- VPC, security group, internet gateway, NAT, private/public subnets
- Endpoints for accessing internet resource from private subnet

### Purpose of the Script

This script automates the management of AWS and GitHub Actions secrets for a project. Its main functions are:

1. **Deploying AWS CloudFormation Stacks:**  
   It can deploy or update a CloudFormation stack (using a YAML template) to set up AWS resources needed before applying further infrastructure changes.

2. **Managing AWS IAM Access Keys:**  
   It generates new AWS IAM access keys for a specified user, ensuring that no more than two keys exist at a time (deleting old ones if necessary).

3. **Pushing Secrets to GitHub Actions:**  
   It securely encrypts and uploads secrets (like AWS credentials, account ID, region, and a generated Postgres password) to a GitHub repository’s Actions secrets, enabling CI/CD workflows to access them securely.

---

### How to Adapt the Script for Your Own Purposes

**1. Change Default Configuration:**  
Edit the following variables at the top of the script to match your environment:
- `IAM_USERNAME`: Your AWS IAM user.
- `AWS_REGION`: Your AWS region.
- `GH_TOKEN`: Set your GitHub token as an environment variable or pass it via `--gh-token`.
- `GITHUB_OWNER` and `REPOSITORY_NAME`: Your GitHub repository details.
- `AWS_PROFILE`: Your AWS CLI profile.
- `PRE_APPLY_SCRIPT`: Path to your CloudFormation YAML template.

**2. Use Command-Line Arguments:**  
Override defaults by passing arguments:
- `--gh-token`: GitHub token.
- `--repo-owner`: GitHub repository owner.
- `--repo-name`: GitHub repository name.
- `--profile`: AWS CLI profile.

---

### Commands for Application Lifecycle

#### **Creating/Deploying an Application**
- **Deploy AWS resources (CloudFormation):**
  ```bash
  python3 script.py --deploy-pre-apply
  ```
  This will create or update the CloudFormation stack as defined in your YAML template.

- **Generate AWS IAM access keys:**
  ```bash
  python3 script.py --generate-key
  ```
  This will create new access keys for the specified IAM user.

- **Push secrets to GitHub Actions:**
  ```bash
  python3 script.py --update-secrets --generate-key
  ```
  This will generate new AWS keys and push them (along with other secrets) to your GitHub repository.

#### **Updating an Application**
- **Update CloudFormation stack:**
  ```bash
  python3 script.py --deploy-pre-apply
  ```
  If your template changes, this will update the stack.

- **Regenerate and update secrets:**
  ```bash
  python3 script.py --generate-key --update-secrets
  ```
  This will rotate AWS keys and update GitHub secrets.

#### **Deleting an Application**
- **Delete AWS resources manually:**  
  The script does not provide a direct delete command. To delete the CloudFormation stack, use AWS CLI:
  ```bash
  aws cloudformation delete-stack --stack-name pre-apply-stack --profile <your-profile> --region <your-region>
  ```
- **Remove GitHub secrets manually:**  
  Use the GitHub UI or API to delete secrets if needed.

---

### Summary Table of Main Commands

| Action                        | Command Example                                                                 |
|-------------------------------|--------------------------------------------------------------------------------|
| Deploy AWS resources          | `python3 script.py --deploy-pre-apply`                                         |
| Generate AWS IAM keys         | `python3 script.py --generate-key`                                             |
| Push/update GitHub secrets    | `python3 script.py --update-secrets --generate-key`                            |
| Delete AWS stack (manual)     | `aws cloudformation delete-stack --stack-name pre-apply-stack ...`              |
| Delete GitHub secrets (manual)| Use GitHub UI or API                                                           |

---

## Github Actions workflow

This workflow automates the deployment of an image application and its authorization service to AWS using CloudFormation and Docker. It is triggered on every push to the `main` branch. The workflow ensures infrastructure is in place, builds and pushes Docker images to AWS ECR, deploys backend and frontend resources, and finally outputs the CloudFront domain for the deployed app.

---

#### **1. Pre-Apply Stack Check (`preapply` job)**
- **Purpose:** Ensures a foundational CloudFormation stack (`pre-apply-stack`) exists before proceeding.
- **Actions:**
  - Configures AWS credentials using secrets.
  - Checks if the stack exists.
  - If missing, deploys it using the template `aws/pre-apply.yaml`.

#### **2. Infrastructure Deployment for ECS (`deployment-pre-build` job)**
- **Purpose:** Prepares infrastructure for running containers (ECS, networking, etc.).
- **Actions:**
  - Checks out the repository code.
  - Configures AWS credentials.
  - Checks if the `family-photos-infra` stack is in a failed state (`ROLLBACK_COMPLETE`). If so, deletes it to allow a clean redeploy.
  - Deploys/updates the infrastructure stack using `aws/cf_infra_pre_build.yaml`.

#### **3. Docker Image Build and Push (`deployment-docker-build` job)**
- **Purpose:** Builds Docker images for the auth service and image app, pushes them to AWS ECR, and records their digests.
- **Actions:**
  - Checks out the code.
  - Configures AWS credentials.
  - Logs in to AWS ECR.
  - Builds and pushes the `auth-service` and `image-app` Docker images.
  - Retrieves and outputs the image digests for later use.

#### **4. Frontend Infrastructure Deployment (`deployment-post-build` job)**
- **Purpose:** Deploys infrastructure needed for the frontend and other post-build resources.
- **Actions:**
  - Checks out the code.
  - Configures AWS credentials.
  - Checks if the `family-photos-infra-post` stack is in a failed state and deletes it if necessary.
  - Deploys/updates the post-build infrastructure stack using `aws/cf_infra_post_build.yaml`, passing parameters like DB credentials and S3 bucket name.

#### **5. Finalization (`finalisation` job)**
- **Purpose:** Retrieves and displays the CloudFront domain name for the deployed application.
- **Actions:**
  - Configures AWS credentials.
  - Gets the CloudFront domain output from the `family-photos-infra` stack and prints it.

---

#### **Deleting**
- **Stack Deletion (manual or scripted):**
  - `aws cloudformation delete-stack --stack-name <name>`
  - `aws cloudformation wait stack-delete-complete --stack-name <name>`
- **Image Deletion (manual):**
  - Use AWS Console or CLI: `aws ecr batch-delete-image ...`

---

