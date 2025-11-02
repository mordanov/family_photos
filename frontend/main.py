# streamlit_app/main.py

import streamlit as st
import requests

API_URL = "http://api-backend.local:8081"
IMAGE_API_URL = "http://image-backend.local:8080"

def login():
    st.title("Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        try:
            resp = requests.post(f"{API_URL}/auth/login", json={"username": username, "password": password}, timeout=10)
            if resp.status_code == 200:
                st.session_state['token'] = resp.json().get('access_token')
                st.session_state['username'] = username
                st.success("Logged in!")
                st.experimental_rerun()
            else:
                st.error("Login failed: " + resp.text)
        except requests.RequestException as e:
            st.error(f"Network error: {e}")

def logout():
    if st.sidebar.button("Logout"):
        st.session_state.clear()
        st.experimental_rerun()

def upload_image():
    st.header("Upload Image")
    uploaded_file = st.file_uploader("Choose an s3-api...", type=["jpg", "jpeg", "png"])
    folder = st.text_input("Subfolder (e.g. cats/2023)", value=st.session_state.get("current_path", ""))
    if uploaded_file and st.button("Upload"):
        files = {'file': (uploaded_file.name, uploaded_file, uploaded_file.type)}
        data = {"folder": folder}
        headers = {}
        try:
            resp = requests.post(f"{IMAGE_API_URL}/images/upload", files=files, data=data, headers=headers, timeout=20)
            if resp.status_code == 200:
                st.success("Image uploaded!")
            else:
                st.error(f"Upload failed: {resp.text}")
        except requests.RequestException as e:
            st.error(f"Network error: {e}")

def browse_folders():
    st.header("Browse Images")
    st.session_state.setdefault("current_path", "")
    path = st.session_state["current_path"]

    params = {"path": path}
    headers = {}
    try:
        resp = requests.get(f"{IMAGE_API_URL}/folders/", params=params, headers=headers, timeout=10)
        if resp.status_code != 200:
            st.error("Failed to load folder contents: " + resp.text)
            return
        data = resp.json()
    except requests.RequestException as e:
        st.error(f"Network error: {e}")
        return

    folders = data.get("folders", [])
    images = data.get("images", [])

    # Navigation
    if path:
        if st.button("⬅️ Up"):
            parent = "/".join(path.strip("/").split("/")[:-1])
            st.session_state["current_path"] = parent
            st.experimental_rerun()

    # Folders
    for folder in folders:
        if st.button(f"📁 {folder}"):
            new_path = f"{path}/{folder}".strip("/")
            st.session_state["current_path"] = new_path
            st.experimental_rerun()

    # Images
    for img in images:
        st.write(img)
        full_path = f"{path}/{img}".strip("/")
        try:
            img_resp = requests.get(f"{IMAGE_API_URL}/images/{full_path}", timeout=10)
            if img_resp.status_code == 200:
                url = img_resp.json().get("url")
                st.image(url, use_column_width=True)
            else:
                st.warning(f"Could not load s3-api: {img}")
        except requests.RequestException as e:
            st.warning(f"Network error loading s3-api {img}: {e}")

def main():
    st.sidebar.title("Image Browser")
    st.session_state.setdefault("token", None)
    st.session_state.setdefault("username", None)
    if not st.session_state["token"]:
        login()
    else:
        st.sidebar.write(f"Logged in as: {st.session_state['username']}")
        logout()
        upload_image()
        browse_folders()

if __name__ == "__main__":
    main()