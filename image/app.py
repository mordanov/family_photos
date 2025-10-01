import os
import requests
import boto3
import streamlit as st
from botocore.exceptions import NoCredentialsError
from PIL import Image
import io

# AWS S3 Configuration
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = "your-region"
BUCKET_NAME = "your-bucket-name"

AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://auth-service:5000/validate-token")  # Auth service within Docker Compose

# Initialize Boto3 Client
s3_client = boto3.client(
    "s3",
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=AWS_REGION,
)


# Middleware: Validate Token from Auth Service
def validate_token():
    auth_header = st.experimental_get_query_params().get("Authorization", [None])[0]
    if not auth_header:
        st.error("Unauthorized: Missing Authorization header.")
        st.stop()

    try:
        response = requests.post(AUTH_SERVICE_URL, headers={"Authorization": auth_header})
        if response.status_code != 200:
            st.error(f"Unauthorized: {response.json().get('error')}")
            st.stop()

        return response.json().get("email")

    except requests.RequestException as e:
        st.error(f"Authorization service unavailable: {e}")
        st.stop()


# Streamlit Interface
st.title("AWS S3 File Manager with Authentication")

# Validate token
user_email = validate_token()
st.sidebar.write(f"Logged in as: {user_email}")

# App functionality (e.g., upload, list, etc.) goes here...