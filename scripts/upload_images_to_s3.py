import os
import sys
import hashlib
import mimetypes
import boto3
from botocore.exceptions import ClientError
import urllib.request
import urllib.error

BUCKET_NAME = "foodbridge-donations-879385476807-v2"
REGION = "ap-south-1"
UPLOADS_DIR = "/var/www/foodbridge/static/uploads"
S3_PREFIX = "donations/"

print("==================================================")
print("Step 17B: S3 Image Upload & Integrity Verification")
print("==================================================")

s3 = boto3.client("s3", region_name=REGION)

# Verify bucket accessibility
try:
    s3.head_bucket(Bucket=BUCKET_NAME)
    print(f"[OK] S3 Bucket '{BUCKET_NAME}' root access is confirmed.")
except ClientError as e:
    err_code = e.response.get("Error", {}).get("Code", "Unknown")
    print(f"[INFO] s3.head_bucket returned {err_code} (expected with scoped 'donations/*' IAM policy).")

files = sorted(os.listdir(UPLOADS_DIR))
print(f"Found {len(files)} files in local {UPLOADS_DIR}:")

uploaded_stats = []

for fname in files:
    local_path = os.path.join(UPLOADS_DIR, fname)
    if not os.path.isfile(local_path):
        continue

    # Calculate local file size and SHA256
    file_size = os.path.getsize(local_path)
    with open(local_path, "rb") as f:
        file_bytes = f.read()
        local_sha256 = hashlib.sha256(file_bytes).hexdigest()

    content_type = mimetypes.guess_type(local_path)[0] or "image/jpeg"
    if fname.lower().endswith((".jpg", ".jpeg")):
        content_type = "image/jpeg"
    s3_key = f"{S3_PREFIX}{fname}"

    print(f"\nProcessing '{fname}':")
    print(f"  Local Size: {file_size} bytes")
    print(f"  Content-Type: {content_type}")
    print(f"  Local SHA256: {local_sha256}")
    print(f"  Target S3 Key: {s3_key}")

    # Upload to S3
    try:
        s3.put_object(
            Bucket=BUCKET_NAME,
            Key=s3_key,
            Body=file_bytes,
            ContentType=content_type,
            ServerSideEncryption="AES256"
        )
        print(f"  [OK] Successfully uploaded to S3: s3://{BUCKET_NAME}/{s3_key}")
    except ClientError as e:
        print(f"  [FAIL] Upload failed: {e}")
        continue

    # Verify retrieval via GetObject
    try:
        resp = s3.get_object(Bucket=BUCKET_NAME, Key=s3_key)
        downloaded_bytes = resp["Body"].read()
        downloaded_sha256 = hashlib.sha256(downloaded_bytes).hexdigest()
        downloaded_size = len(downloaded_bytes)
        downloaded_content_type = resp.get("ContentType")
        downloaded_sse = resp.get("ServerSideEncryption")

        match_sha = (downloaded_sha256 == local_sha256)
        match_size = (downloaded_size == file_size)
        match_ct = (downloaded_content_type == "image/jpeg")

        print(f"  Verification via s3:GetObject:")
        print(f"    Downloaded Size: {downloaded_size} bytes (Match: {match_size})")
        print(f"    Downloaded SHA256: {downloaded_sha256} (Match: {match_sha})")
        print(f"    ContentType: {downloaded_content_type} (Match: {match_ct})")
        print(f"    ServerSideEncryption: {downloaded_sse}")

        if match_sha and match_size and match_ct:
            print(f"  [VERIFIED] Integrity 100% confirmed for {s3_key}")
            uploaded_stats.append({
                "filename": fname,
                "s3_key": s3_key,
                "size": file_size,
                "sha256": local_sha256,
                "content_type": downloaded_content_type,
                "sse": downloaded_sse,
                "status": "VERIFIED"
            })
        else:
            print(f"  [FAIL] Integrity mismatch!")
    except ClientError as e:
        print(f"  [FAIL] GetObject verification failed: {e}")

# Verify objects are not public
print("\n--- Public Access Test (Simulating Unauthenticated Access) ---")
for stat in uploaded_stats:
    public_url = f"https://{BUCKET_NAME}.s3.{REGION}.amazonaws.com/{stat['s3_key']}"
    try:
        req = urllib.request.Request(public_url, method="GET")
        with urllib.request.urlopen(req) as resp:
            print(f"  [WARNING] Object {stat['s3_key']} is publicly accessible! HTTP {resp.status}")
    except urllib.error.HTTPError as e:
        if e.code == 403:
            print(f"  [CONFIRMED PRIVATE] Object {stat['s3_key']} returned HTTP 403 Forbidden ({e.reason}) - Public access blocked.")
        else:
            print(f"  Object {stat['s3_key']} returned HTTP {e.code}: {e.reason}")
    except Exception as e:
        print(f"  Error probing public URL: {e}")

print("\n==================================================")
print("Step 17B Upload and Integrity Verification Summary")
print("==================================================")
print(f"Total files uploaded and verified: {len(uploaded_stats)} / {len(files)}")
for s in uploaded_stats:
    print(f"  - {s['filename']}: Size={s['size']} B | SHA256={s['sha256']} | ContentType={s['content_type']} | SSE={s['sse']} | Status={s['status']}")
print("==================================================")
