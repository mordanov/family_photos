import os
import requests
import boto3
import streamlit as st

# AWS S3 Configuration
AWS_REGION = os.getenv("AWS_REGION")
BUCKET_NAME = os.getenv("BUCKET_NAME", "photo-mordanov")

# Auth Service URL (should be the internal ECS service DNS name and port)
AUTH_SERVICE_URL = os.getenv(
    "AUTH_SERVICE_URL",
    "http://auth-service:8080/api/auth/validate-token"
)

# Initialize Boto3 Client
s3_client = boto3.client(
    "s3",
    region_name=AWS_REGION,
)

def validate_token():
    # Streamlit's query_params returns a dict of lists
    auth_header = st.query_params.get("Authorization", [None])[0]
    if not auth_header:
        st.error("Unauthorized: Missing Authorization header.")
        st.stop()

    try:
        response = requests.post(
            AUTH_SERVICE_URL,
            headers={"Authorization": auth_header},
            timeout=5
        )
        if response.status_code != 200:
            # Try to extract error message, fallback to status code
            try:
                error_msg = response.json().get("error", response.text)
            except Exception:
                error_msg = response.text
            st.error(f"Unauthorized: {error_msg}")
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