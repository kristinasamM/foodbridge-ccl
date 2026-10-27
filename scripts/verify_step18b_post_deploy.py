#!/usr/bin/env python3
"""
Step 18B Post-Deployment Health Check Script
Verifies:
1. Flask configuration (USE_SNS, USE_S3, USE_SECRETS_MANAGER, SNS_TOPIC_ARN)
2. Database engine is MySQL (dialect mysql)
3. Database record counts (Users, Donations, Reservations)
4. S3 image retrieval (generate presigned URL and fetch HTTP 200)
"""
import os
import sys

# Ensure production app directory is first in path
sys.path.insert(0, "/var/www/foodbridge")

env_file = "/var/www/foodbridge/.env"
if os.path.exists(env_file):
    with open(env_file, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip()

from app import app, db, User, Donation, Reservation, get_s3_client, get_sns_client

def main():
    print("=" * 60)
    print("FOODBRIDGE STEP 18B POST-DEPLOYMENT VERIFICATION")
    print("=" * 60)

    with app.app_context():
        # 1. Config Check
        print("[1] Configuration:")
        print(f"    USE_SNS: {app.config.get('USE_SNS')}")
        print(f"    SNS_TOPIC_ARN: {app.config.get('SNS_TOPIC_ARN')}")
        print(f"    USE_S3: {app.config.get('USE_S3')}")
        print(f"    S3_BUCKET: {app.config.get('S3_BUCKET')}")
        print(f"    USE_SECRETS_MANAGER: {os.environ.get('USE_SECRETS_MANAGER')}")

        assert app.config.get("USE_SNS") is True, "USE_SNS must be True!"
        assert app.config.get("SNS_TOPIC_ARN") == "arn:aws:sns:ap-south-1:879385476807:foodbridge-notifications", "Invalid SNS_TOPIC_ARN!"
        assert app.config.get("USE_S3") is True, "USE_S3 must be True!"

        # 2. Database Engine Check
        engine_dialect = db.engine.dialect.name
        print(f"\n[2] Database Engine Dialect: {engine_dialect}")
        assert engine_dialect == "mysql", f"Engine must be mysql, found {engine_dialect}!"

        # 3. Database Record Counts (Must match pre-deployment counts)
        user_count = User.query.count()
        donation_count = Donation.query.count()
        reservation_count = Reservation.query.count()

        print(f"\n[3] Database Record Counts:")
        print(f"    Users: {user_count} (Expected: 7)")
        print(f"    Donations: {donation_count} (Expected: 4)")
        print(f"    Reservations: {reservation_count} (Expected: 1)")

        assert user_count == 7, f"User count changed! Found {user_count}"
        assert donation_count == 4, f"Donation count changed! Found {donation_count}"
        assert reservation_count == 1, f"Reservation count changed! Found {reservation_count}"

        # 4. S3 Image Retrieval
        print("\n[4] S3 Image Retrieval Test:")
        sample_donation = Donation.query.filter(Donation.image_filename.isnot(None)).first()
        if sample_donation and sample_donation.image_filename:
            print(f"    Testing with donation ID {sample_donation.id}: {sample_donation.image_filename}")
            s3 = get_s3_client()
            bucket = app.config.get("S3_BUCKET")
            s3_key = f"donations/{sample_donation.image_filename}"
            # Check object exists
            head_resp = s3.head_object(Bucket=bucket, Key=s3_key)
            print(f"    S3 HeadObject ContentLength: {head_resp.get('ContentLength')} bytes")
            print(f"    S3 HeadObject ServerSideEncryption: {head_resp.get('ServerSideEncryption')}")

            # Generate presigned URL
            presigned_url = s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket, "Key": s3_key},
                ExpiresIn=300,
            )
            import urllib.request
            req = urllib.request.urlopen(presigned_url, timeout=5)
            print(f"    Presigned URL HTTP Status: {req.getcode()}")
            assert req.getcode() == 200, "Presigned URL fetch failed!"
            print("    S3 image retrieval is working perfectly.")
        else:
            print("    WARNING: No donation with image found.")

    print("\n" + "=" * 60)
    print("ALL POST-DEPLOYMENT HEALTH CHECKS PASSED SUCCESSFULLY!")
    print("=" * 60)

if __name__ == "__main__":
    main()
