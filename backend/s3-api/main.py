import os

from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Query
from typing import List, Dict
import boto3


# AWS S3 Configuration
AWS_REGION = os.getenv("AWS_REGION")
BUCKET_NAME = os.getenv("BUCKET_NAME", "photo-mordanov")

app = FastAPI()

s3 = boto3.client(
    "s3",
    region_name=AWS_REGION
)

@app.get("/")
async def health_check():
    return {"status": "ok"}

@app.post("/images/upload")
def upload_image(file: UploadFile = File(...), folder: str = Form("")):
    key = f"{folder.strip('/')}/{file.filename}" if folder else file.filename
    try:
        s3.upload_fileobj(file.file, BUCKET_NAME, key)
        return {"msg": "Uploaded", "key": key}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/images/{full_path:path}")
def get_image(full_path: str):
    try:
        url = s3.generate_presigned_url(
            'get_object',
            Params={'Bucket': BUCKET_NAME, 'Key': full_path},
            ExpiresIn=3600
        )
        return {"url": url}
    except Exception:
        raise HTTPException(status_code=404, detail="Image not found")

@app.delete("/images/{full_path:path}")
def delete_image(full_path: str):
    try:
        s3.delete_object(Bucket=S3_BUCKET, Key=full_path)
        return {"msg": "Deleted"}
    except Exception:
        raise HTTPException(status_code=404, detail="Image not found")

@app.get("/folders/")
def list_folder(path: str = Query(default="")) -> Dict[str, List[str]]:
    paginator = s3.get_paginator('list_objects_v2')
    prefix = path.strip("/") + "/" if path else ""
    result = paginator.paginate(Bucket=BUCKET_NAME, Prefix=prefix, Delimiter='/')
    folders = []
    images = []
    for page in result:
        # Subfolders
        for cp in page.get('CommonPrefixes', []):
            folder_name = cp['Prefix'][len(prefix):].strip("/")
            folders.append(folder_name)
        # Images/files
        for obj in page.get('Contents', []):
            key = obj['Key']
            if key.endswith('/'):
                continue  # skip folder keys
            name = key[len(prefix):]
            if "/" not in name:  # only direct children
                images.append(name)
    return {"folders": folders, "images": images}