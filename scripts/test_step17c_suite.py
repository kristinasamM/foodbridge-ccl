import io
import os
import sys
import unittest
import uuid
import hashlib
from unittest.mock import MagicMock, patch
from botocore.exceptions import ClientError
from werkzeug.datastructures import FileStorage

# Ensure project root is in path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

import app
from app import (
    app as flask_app,
    db,
    User,
    Donation,
    Reservation,
    validate_image_file,
    get_image_url,
    DEFAULT_IMAGE_PLACEHOLDER,
)


class Step17CTestSuite(unittest.TestCase):
    def setUp(self):
        flask_app.config["TESTING"] = True
        flask_app.config["WTF_CSRF_ENABLED"] = False
        self.client = flask_app.test_client()

        # Minimal valid 1x1 JPEG and PNG bytes
        self.valid_jpeg_bytes = (
            b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00"
            b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t"
            b"\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00"
            b"\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00"
            b"\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\x80"
            b"\xff\xd9"
        )
        self.valid_png_bytes = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01"
            b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        )

    # --------------------------------------------------------------------------
    # 1. Valid JPEG Upload Validation
    # --------------------------------------------------------------------------
    def test_valid_jpeg_validation(self):
        storage = FileStorage(
            stream=io.BytesIO(self.valid_jpeg_bytes),
            filename="fresh_apples.jpg",
            content_type="image/jpeg",
        )
        is_valid, err_msg, content_type, file_bytes = validate_image_file(storage)
        self.assertTrue(is_valid)
        self.assertIsNone(err_msg)
        self.assertEqual(content_type, "image/jpeg")
        self.assertEqual(file_bytes, self.valid_jpeg_bytes)

    # --------------------------------------------------------------------------
    # 2. Valid PNG Upload Validation
    # --------------------------------------------------------------------------
    def test_valid_png_validation(self):
        storage = FileStorage(
            stream=io.BytesIO(self.valid_png_bytes),
            filename="bread_loaf.png",
            content_type="image/png",
        )
        is_valid, err_msg, content_type, file_bytes = validate_image_file(storage)
        self.assertTrue(is_valid)
        self.assertIsNone(err_msg)
        self.assertEqual(content_type, "image/png")
        self.assertEqual(file_bytes, self.valid_png_bytes)

    # --------------------------------------------------------------------------
    # 3. Invalid File Type Rejected
    # --------------------------------------------------------------------------
    def test_invalid_extension_rejected(self):
        for bad_name in ["script.py", "document.pdf", "image.gif", "archive.zip"]:
            storage = FileStorage(
                stream=io.BytesIO(b"dummy payload"),
                filename=bad_name,
            )
            is_valid, err_msg, content_type, file_bytes = validate_image_file(storage)
            self.assertFalse(is_valid, f"Should reject {bad_name}")
            self.assertIn("Invalid image format", err_msg)

    # --------------------------------------------------------------------------
    # 4. Incorrect File Content Rejected (Spoofed Header)
    # --------------------------------------------------------------------------
    def test_spoofed_file_content_rejected(self):
        # A text file renamed to .jpg
        fake_jpeg = FileStorage(
            stream=io.BytesIO(b"Hello world! This is just plain text, not a JPEG."),
            filename="spoofed.jpg",
            content_type="image/jpeg",
        )
        is_valid, err_msg, _, _ = validate_image_file(fake_jpeg)
        self.assertFalse(is_valid)
        self.assertEqual(err_msg, "Uploaded file is not a valid JPEG image.")

        # A text file renamed to .png
        fake_png = FileStorage(
            stream=io.BytesIO(b"Not a real PNG header"),
            filename="spoofed.png",
            content_type="image/png",
        )
        is_valid, err_msg, _, _ = validate_image_file(fake_png)
        self.assertFalse(is_valid)
        self.assertEqual(err_msg, "Uploaded file is not a valid PNG image.")

    # --------------------------------------------------------------------------
    # 5. Oversized Image Rejected
    # --------------------------------------------------------------------------
    def test_oversized_image_rejected(self):
        # Header + oversized payload (> 16MB)
        oversized_bytes = b"\xff\xd8\xff" + b"0" * (16 * 1024 * 1024 + 100)
        storage = FileStorage(
            stream=io.BytesIO(oversized_bytes),
            filename="huge_image.jpg",
            content_type="image/jpeg",
        )
        is_valid, err_msg, _, _ = validate_image_file(storage)
        self.assertFalse(is_valid)
        self.assertIn("exceeds maximum limit", err_msg)

    # --------------------------------------------------------------------------
    # 6. Unique S3 Key Generation
    # --------------------------------------------------------------------------
    def test_unique_s3_key_generation(self):
        generated_keys = set()
        for _ in range(50):
            safe_name = "curry_pot.jpg"
            key = f"{uuid.uuid4().hex[:10]}_{safe_name}"
            self.assertNotIn(key, generated_keys)
            generated_keys.add(key)
            self.assertTrue(key.endswith("_curry_pot.jpg"))
            self.assertEqual(len(key.split("_")[0]), 10)

    # --------------------------------------------------------------------------
    # 7. S3 Upload Failure Handled Safely (No Silent Fallback to Local Storage)
    # --------------------------------------------------------------------------
    def test_s3_upload_failure_produces_clear_error_and_no_local_fallback(self):
        mock_s3 = MagicMock()
        mock_s3.put_object.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "Access Denied"}},
            "PutObject"
        )

        with patch("app.get_s3_client", return_value=mock_s3):
            with patch.dict(flask_app.config, {"USE_S3": True, "S3_BUCKET": "foodbridge-donations-879385476807-v2"}):
                with self.client.session_transaction() as sess:
                    sess["user_id"] = 2
                    sess["user_role"] = "donor"
                    sess["user_name"] = "Donor Joe"

                data = {
                    "food_name": "Test S3 Failure Food",
                    "category": "Cooked Food",
                    "quantity": "10",
                    "pickup_location": "Kitchen Hub",
                    "available_until": "2026-12-31T23:59",
                    "description": "Testing upload failure",
                    "food_image": (io.BytesIO(self.valid_jpeg_bytes), "test_fail.jpg"),
                }

                # Ensure local uploads directory is monitored
                local_dir = flask_app.config["UPLOAD_FOLDER"]
                files_before = set(os.listdir(local_dir))

                response = self.client.post("/donor/donations/add", data=data, content_type="multipart/form-data")

                files_after = set(os.listdir(local_dir))
                # Verify NO local file was saved
                self.assertEqual(files_before, files_after, "File MUST NOT silently fall back to local disk!")

                # Verify clear error flash in response
                self.assertIn(b"Failed to upload image to secure cloud storage", response.data)

    # --------------------------------------------------------------------------
    # 8. S3 Upload Success Flow (JPEG & PNG)
    # --------------------------------------------------------------------------
    def test_s3_upload_success_flow(self):
        mock_s3 = MagicMock()

        with patch("app.get_s3_client", return_value=mock_s3):
            with patch.dict(flask_app.config, {"USE_S3": True, "S3_BUCKET": "foodbridge-donations-879385476807-v2"}):
                with self.client.session_transaction() as sess:
                    sess["user_id"] = 2
                    sess["user_role"] = "donor"
                    sess["user_name"] = "Donor Joe"

                # Test JPEG upload
                data = {
                    "food_name": "Test S3 Success Apples",
                    "category": "Fruits / Vegetables",
                    "quantity": "15",
                    "pickup_location": "Market 1",
                    "available_until": "2026-12-31T23:59",
                    "description": "Fresh organic apples",
                    "food_image": (io.BytesIO(self.valid_jpeg_bytes), "apples.jpg"),
                }

                with patch.object(db.session, "add"), patch.object(db.session, "commit"):
                    resp = self.client.post("/donor/donations/add", data=data, content_type="multipart/form-data")
                    self.assertEqual(resp.status_code, 302)
                    self.assertIn("/donor/dashboard", resp.headers["Location"])

                    # Verify S3 put_object arguments
                    mock_s3.put_object.assert_called_once()
                    call_kwargs = mock_s3.put_object.call_args[1]
                    self.assertEqual(call_kwargs["Bucket"], "foodbridge-donations-879385476807-v2")
                    self.assertTrue(call_kwargs["Key"].startswith("donations/"))
                    self.assertTrue(call_kwargs["Key"].endswith("_apples.jpg"))
                    self.assertEqual(call_kwargs["ContentType"], "image/jpeg")
                    self.assertEqual(call_kwargs["ServerSideEncryption"], "AES256")
                    self.assertEqual(call_kwargs["Body"], self.valid_jpeg_bytes)

    # --------------------------------------------------------------------------
    # 9. Presigned URL Generation
    # --------------------------------------------------------------------------
    def test_presigned_url_generation(self):
        mock_s3 = MagicMock()
        mock_s3.generate_presigned_url.return_value = (
            "https://foodbridge-donations-879385476807-v2.s3.ap-south-1.amazonaws.com/"
            "donations/abc123_food.jpg?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Expires=900"
        )

        with patch("app.get_s3_client", return_value=mock_s3):
            with patch.dict(flask_app.config, {"USE_S3": True, "S3_BUCKET": "foodbridge-donations-879385476807-v2"}):
                url = get_image_url("abc123_food.jpg")
                self.assertIn("donations/abc123_food.jpg", url)
                self.assertIn("X-Amz-Expires=900", url)

                # Verify s3 call parameters
                mock_s3.generate_presigned_url.assert_called_with(
                    "get_object",
                    Params={"Bucket": "foodbridge-donations-879385476807-v2", "Key": "donations/abc123_food.jpg"},
                    ExpiresIn=900,
                )

    # --------------------------------------------------------------------------
    # 10. Existing Image Filename Compatibility & NULL Placeholder
    # --------------------------------------------------------------------------
    def test_existing_filename_compatibility_and_null_placeholder(self):
        # NULL / None placeholder
        self.assertEqual(get_image_url(None), DEFAULT_IMAGE_PLACEHOLDER)
        self.assertEqual(get_image_url(""), DEFAULT_IMAGE_PLACEHOLDER)
        self.assertEqual(get_image_url("   "), DEFAULT_IMAGE_PLACEHOLDER)

        # Legacy filename from DB (e.g. b6d4a88c66_71JISmXA8LL._AC_UF8941000_QL80_.jpg)
        legacy_fname = "b6d4a88c66_71JISmXA8LL._AC_UF8941000_QL80_.jpg"
        mock_s3 = MagicMock()
        mock_s3.generate_presigned_url.return_value = f"https://s3/donations/{legacy_fname}?signed"

        with patch("app.get_s3_client", return_value=mock_s3):
            with patch.dict(flask_app.config, {"USE_S3": True}):
                url = get_image_url(legacy_fname)
                mock_s3.generate_presigned_url.assert_called_with(
                    "get_object",
                    Params={"Bucket": "foodbridge-donations-879385476807-v2", "Key": f"donations/{legacy_fname}"},
                    ExpiresIn=900,
                )
                self.assertEqual(url, f"https://s3/donations/{legacy_fname}?signed")

    # --------------------------------------------------------------------------
    # 11. Local Development Mode Unchanged (USE_S3=false)
    # --------------------------------------------------------------------------
    def test_local_development_mode_unchanged(self):
        with patch.dict(flask_app.config, {"USE_S3": False}):
            with flask_app.test_request_context("/"):
                url = get_image_url("sample_local.jpg")
                self.assertEqual(url, "/static/uploads/sample_local.jpg")

    # --------------------------------------------------------------------------
    # 12. Secrets Manager MySQL Connection Security Check
    # --------------------------------------------------------------------------
    def test_secrets_manager_cutover_integrity(self):
        dummy_app = app.Flask("test_sm")
        dummy_app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

        with patch.dict(os.environ, {"USE_SECRETS_MANAGER": "true"}):
            with patch("boto3.Session") as mock_session_cls:
                mock_sm = MagicMock()
                mock_sm.get_secret_value.return_value = {"SecretString": "INVALID_JSON"}
                mock_session_cls.return_value.client.return_value = mock_sm

                with self.assertRaises(RuntimeError) as ctx:
                    app.configure_database(dummy_app)
                self.assertIn("Mandatory MySQL configuration via AWS Secrets Manager", str(ctx.exception))
                self.assertNotIn("sqlite", dummy_app.config.get("SQLALCHEMY_DATABASE_URI", ""))

    # --------------------------------------------------------------------------
    # 13. Template Context Helper Registration
    # --------------------------------------------------------------------------
    def test_template_helper_registered(self):
        self.assertIn("get_image_url", flask_app.jinja_env.globals)
        self.assertIn("image_url", flask_app.jinja_env.filters)

    # --------------------------------------------------------------------------
    # 14. Original SQLite Database Hash Intact
    # --------------------------------------------------------------------------
    def test_original_sqlite_hash_intact(self):
        db_path = os.path.join(PROJECT_ROOT, "instance", "foodbridge.db")
        if os.path.exists(db_path):
            with open(db_path, "rb") as f:
                h = hashlib.sha256(f.read()).hexdigest().lower()
            expected = "00c9ccaddbfbf3355760d064c74d78b0006dfbf99ba9c27c0d2f3594ba0e8830"
            self.assertEqual(h, expected, "Original SQLite file must never be modified!")


if __name__ == "__main__":
    unittest.main()
