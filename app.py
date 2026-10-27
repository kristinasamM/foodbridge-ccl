import os
import re
import uuid
from datetime import datetime, timezone, timedelta
try:
    from zoneinfo import ZoneInfo
    IST_TZ = ZoneInfo("Asia/Kolkata")
except Exception:
    IST_TZ = timezone(timedelta(hours=5, minutes=30))
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "foodbridge-secret-key-local-development")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False


def configure_database(flask_app):
    """
    Configures SQLAlchemy database URI and connection engine options safely.

    Modes:
    1. Mandatory MySQL via AWS Secrets Manager:
       Activated when USE_SECRETS_MANAGER=true.
       Retrieves credentials strictly in-memory from AWS Secrets Manager using IAM authentication.
       Ignores any legacy SQLite DATABASE_URL settings to prevent accidental SQLite usage in production.
       If Secrets Manager retrieval or credential validation fails, raises a clear RuntimeError.
       NEVER silently falls back to SQLite.

    2. Local Development Mode:
       Used when USE_SECRETS_MANAGER is unset or false.
       Uses DATABASE_URL if explicitly set (e.g. for testing disposable databases).
       Defaults to 'sqlite:///foodbridge.db'.
    """
    use_sm = os.environ.get("USE_SECRETS_MANAGER", "").strip().lower() in ("true", "1", "yes")

    if use_sm:
        secret_name = os.environ.get("RDS_SECRET_NAME", "foodbridge/app-db-credentials")
        region = os.environ.get("AWS_REGION", "ap-south-1")
        try:
            import boto3
            import json
            from sqlalchemy.engine import URL

            profile = os.environ.get("AWS_PROFILE")
            session = (
                boto3.Session(profile_name=profile, region_name=region)
                if profile
                else boto3.Session(region_name=region)
            )
            sm_client = session.client("secretsmanager")

            resp = sm_client.get_secret_value(SecretId=secret_name)
            if "SecretString" not in resp:
                raise ValueError(f"Secret '{secret_name}' does not contain SecretString.")

            secret_data = json.loads(resp["SecretString"])
            username = secret_data.get("username")
            password = secret_data.get("password")
            host = secret_data.get("host")
            port = int(secret_data.get("port", 3306))
            dbname = secret_data.get("dbname") or secret_data.get("database")

            if not all([username, password, host, dbname]):
                missing = [
                    k
                    for k, v in [
                        ("username", username),
                        ("password", password),
                        ("host", host),
                        ("dbname", dbname),
                    ]
                    if not v
                ]
                raise ValueError(
                    f"Secret '{secret_name}' is missing required fields: {missing}"
                )

            url_obj = URL.create(
                drivername="mysql+pymysql",
                username=username,
                password=password,
                host=host,
                port=port,
                database=dbname,
                query={"charset": "utf8mb4"},
            )
            # Assign connection URL entirely in-memory (passwords are never logged or stored to disk)
            flask_app.config["SQLALCHEMY_DATABASE_URI"] = url_obj.render_as_string(
                hide_password=False
            )
        except Exception as e:
            # Fatal startup error: MySQL is mandatory in Secrets Manager mode. Silent SQLite fallback is strictly prohibited.
            raise RuntimeError(
                f"[FATAL] Mandatory MySQL configuration via AWS Secrets Manager ('{secret_name}') failed: {e}. "
                f"Startup aborted to prevent silent fallback to SQLite."
            ) from e
    else:
        # Local development fallback
        raw_db_url = os.environ.get("DATABASE_URL")
        if raw_db_url:
            flask_app.config["SQLALCHEMY_DATABASE_URI"] = raw_db_url
        else:
            flask_app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///foodbridge.db"

    # Connection pooling options for MySQL RDS
    if flask_app.config["SQLALCHEMY_DATABASE_URI"].startswith("mysql"):
        flask_app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
            "pool_recycle": 280,
            "pool_pre_ping": True,
        }


configure_database(app)

app.config["UPLOAD_FOLDER"] = os.path.join(app.root_path, "static", "uploads")
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB max file upload size

# S3 Storage Configuration
app.config["USE_S3"] = os.environ.get("USE_S3", "").strip().lower() in ("true", "1", "yes")
app.config["S3_BUCKET"] = os.environ.get("S3_BUCKET", "foodbridge-donations-879385476807-v2")
app.config["AWS_REGION"] = os.environ.get("AWS_REGION", "ap-south-1")
app.config["S3_PRESIGNED_EXPIRY"] = int(os.environ.get("S3_PRESIGNED_EXPIRY", "900"))  # 15 minutes

# SNS Notification Configuration
app.config["USE_SNS"] = os.environ.get("USE_SNS", "").strip().lower() in ("true", "1", "yes")
app.config["SNS_TOPIC_ARN"] = os.environ.get(
    "SNS_TOPIC_ARN", "arn:aws:sns:ap-south-1:879385476807:foodbridge-notifications"
)

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png"}
DONATION_CATEGORIES = [
    "Cooked Food",
    "Packaged Food",
    "Bakery",
    "Fruits / Vegetables",
    "Other",
]

os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

db = SQLAlchemy(app)

_s3_client = None


def get_s3_client():
    """
    Returns a singleton boto3 S3 client using EC2 IAM Role or configured session.
    Credentials are never hardcoded.
    Configured with regional endpoint and SigV4 for accurate presigned URLs.
    """
    global _s3_client
    if _s3_client is None:
        import boto3
        from botocore.client import Config

        region = app.config.get("AWS_REGION") or os.environ.get("AWS_REGION") or "ap-south-1"
        profile = os.environ.get("AWS_PROFILE")
        if profile:
            session = boto3.Session(profile_name=profile, region_name=region)
        else:
            session = boto3.Session(region_name=region)
        _s3_client = session.client(
            "s3",
            region_name=region,
            endpoint_url=f"https://s3.{region}.amazonaws.com",
            config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
        )
    return _s3_client


# SNS Client & Notification Helpers
_sns_client = None

SUPPORTED_SNS_EVENTS = {
    "DONATION_CREATED",
    "DONATION_RESERVED",
    "DONATION_COLLECTED",
    "DONATION_EXPIRED",
}


def get_sns_client():
    """
    Returns a singleton boto3 SNS client using EC2 IAM Role or configured session.
    Credentials are never hardcoded. Configured with a 5-second connect/read timeout.
    """
    global _sns_client
    if _sns_client is None:
        import boto3
        from botocore.config import Config

        region = app.config.get("AWS_REGION") or os.environ.get("AWS_REGION") or "ap-south-1"
        profile = os.environ.get("AWS_PROFILE")
        timeout_config = Config(connect_timeout=5, read_timeout=5, retries={"max_attempts": 2})

        if profile:
            session = boto3.Session(profile_name=profile, region_name=region)
        else:
            session = boto3.Session(region_name=region)

        _sns_client = session.client("sns", region_name=region, config=timeout_config)
    return _sns_client


def build_sns_message(event_type, **kwargs):
    """
    Builds a sanitized, human-readable notification subject and message body.
    Excludes sensitive user credentials, password hashes, and exact street addresses.
    """
    if event_type == "DONATION_CREATED":
        donation = kwargs.get("donation")
        subject = f"[FoodBridge] New Donation Available: {donation.food_name[:50]}"
        body = (
            f"A new food donation has been posted on FoodBridge!\n\n"
            f"• Donation ID: #{donation.id}\n"
            f"• Food Item: {donation.food_name}\n"
            f"• Category: {donation.category}\n"
            f"• Quantity: {donation.quantity} servings/units\n"
            f"• Area / Location: {donation.pickup_location}\n"
            f"• Available Until: {donation.available_until}\n\n"
            f"Log in to the FoodBridge NGO Dashboard to view details and reserve:\n"
            f"http://13.206.208.91/login\n"
        )
        return subject, body

    elif event_type == "DONATION_RESERVED":
        donation = kwargs.get("donation")
        ngo_name = kwargs.get("ngo_name", "An NGO Partner")
        subject = f"[FoodBridge] Donation Reserved: {donation.food_name[:50]}"
        body = (
            f"A food donation has been reserved by an NGO partner.\n\n"
            f"• Donation ID: #{donation.id}\n"
            f"• Food Item: {donation.food_name}\n"
            f"• Reserved By: {ngo_name}\n"
            f"• Pickup Location: {donation.pickup_location}\n"
            f"• Status: RESERVED\n\n"
            f"Please prepare the food items for collection.\n"
        )
        return subject, body

    elif event_type == "DONATION_COLLECTED":
        donation = kwargs.get("donation")
        subject = f"[FoodBridge] Donation Collected: {donation.food_name[:50]}"
        body = (
            f"Great news! A reserved donation has been successfully picked up and collected.\n\n"
            f"• Donation ID: #{donation.id}\n"
            f"• Food Item: {donation.food_name}\n"
            f"• Status: COMPLETED\n\n"
            f"Thank you for helping reduce food waste and feed those in need!\n"
        )
        return subject, body

    elif event_type == "DONATION_EXPIRED":
        donation = kwargs.get("donation")
        subject = f"[FoodBridge] Donation Expired: {donation.food_name[:50]}"
        body = (
            f"Notification: A food donation has reached its expiration window without being collected.\n\n"
            f"• Donation ID: #{donation.id}\n"
            f"• Food Item: {donation.food_name}\n"
            f"• Expiry Window: {donation.available_until}\n"
            f"• Status: EXPIRED\n"
        )
        return subject, body

    else:
        raise ValueError(f"Unsupported SNS event type: {event_type}")


def publish_sns_notification(event_type, **kwargs):
    """
    Publishes an SNS notification for supported FoodBridge events.
    - Non-blocking: failures are logged and do not roll back database commits.
    - Returns (success: bool, message_id: str or None)
    """
    use_sns = app.config.get("USE_SNS", False) or os.environ.get("USE_SNS", "").strip().lower() in ("true", "1", "yes")
    if not use_sns:
        return False, None

    if event_type not in SUPPORTED_SNS_EVENTS:
        app.logger.warning(f"Ignoring unsupported SNS event type: {event_type}")
        return False, None

    topic_arn = app.config.get("SNS_TOPIC_ARN") or os.environ.get(
        "SNS_TOPIC_ARN", "arn:aws:sns:ap-south-1:879385476807:foodbridge-notifications"
    )

    try:
        subject, body = build_sns_message(event_type, **kwargs)
        client = get_sns_client()
        resp = client.publish(
            TopicArn=topic_arn,
            Subject=subject[:100],  # AWS SNS Subject limit is 100 characters
            Message=body,
            MessageAttributes={
                "event_type": {"DataType": "String", "StringValue": event_type}
            },
        )
        message_id = resp.get("MessageId")
        app.logger.info(f"SNS notification published for {event_type} [MessageId: {message_id}]")
        return True, message_id
    except Exception as e:
        app.logger.warning(f"Non-blocking SNS publish failed for {event_type}: {type(e).__name__}")
        return False, None



def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def validate_image_file(file_storage):
    """
    Validates that the uploaded file is a genuine JPEG or PNG image within size limits.
    Returns (is_valid: bool, error_message: str or None, content_type: str or None, file_bytes: bytes or None)
    """
    if not file_storage or not file_storage.filename:
        return False, "No file selected.", None, None

    filename = file_storage.filename
    if "." not in filename:
        return False, "File has no extension.", None, None

    ext = filename.rsplit(".", 1)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return False, "Invalid image format. Allowed formats: jpg, jpeg, png.", None, None

    file_bytes = file_storage.read()
    file_storage.seek(0)

    if len(file_bytes) == 0:
        return False, "Uploaded image file is empty.", None, None

    if len(file_bytes) > app.config["MAX_CONTENT_LENGTH"]:
        return False, "Image file exceeds maximum limit of 16 MB.", None, None

    # Header & Magic byte verification
    if ext in ("jpg", "jpeg"):
        if not file_bytes.startswith(b"\xff\xd8\xff"):
            return False, "Uploaded file is not a valid JPEG image.", None, None
        return True, None, "image/jpeg", file_bytes

    if ext == "png":
        if not file_bytes.startswith(b"\x89PNG\r\n\x1a\n") or b"IHDR" not in file_bytes[:32]:
            return False, "Uploaded file is not a valid PNG image.", None, None
        return True, None, "image/png", file_bytes

    return False, "Unsupported image type.", None, None


DEFAULT_IMAGE_PLACEHOLDER = "data:image/svg+xml;charset=UTF-8,%3Csvg%20width%3D%2264%22%20height%3D%2264%22%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%3E%3Crect%20width%3D%22100%25%22%20height%3D%22100%25%22%20fill%3D%22%23e9ecef%22%2F%3E%3Ctext%20x%3D%2250%25%22%20y%3D%2250%25%22%20dominant-baseline%3D%22middle%22%20text-anchor%3D%22middle%22%20font-family%3D%22sans-serif%22%20font-size%3D%2210%22%20fill%3D%22%236c757d%22%3ENo%20Image%3C%2Ftext%3E%3C%2Fsvg%3E"


def get_image_url(image_filename):
    """
    Returns the URL for a donation image.
    - If image_filename is NULL / None / empty: returns an appropriate placeholder.
    - When USE_S3=true: generates a 15-minute presigned GET URL under 'donations/<filename>'.
    - When USE_S3=false: returns the local /static/uploads/<filename> URL.
    - Handles errors safely without exposing sensitive credentials or S3 internals.
    """
    if not image_filename or not str(image_filename).strip():
        return DEFAULT_IMAGE_PLACEHOLDER

    clean_filename = os.path.basename(str(image_filename).strip())

    use_s3 = app.config.get("USE_S3", False) or os.environ.get("USE_S3", "").strip().lower() in ("true", "1", "yes")

    if use_s3:
        bucket = app.config.get("S3_BUCKET") or os.environ.get("S3_BUCKET", "foodbridge-donations-879385476807-v2")
        expiry = app.config.get("S3_PRESIGNED_EXPIRY", 900)
        s3_key = f"donations/{clean_filename}"
        try:
            client = get_s3_client()
            presigned_url = client.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket, "Key": s3_key},
                ExpiresIn=expiry,
            )
            return presigned_url
        except Exception as e:
            app.logger.error(f"Failed to generate presigned S3 URL for {s3_key}: {type(e).__name__}")
            return DEFAULT_IMAGE_PLACEHOLDER

    try:
        return url_for("static", filename=f"uploads/{clean_filename}")
    except Exception:
        return f"/static/uploads/{clean_filename}"


@app.context_processor
def inject_image_url_helper():
    return dict(get_image_url=get_image_url)


app.jinja_env.globals["get_image_url"] = get_image_url
app.jinja_env.filters["image_url"] = get_image_url


# Models
class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'donor', 'ngo', 'admin'

    def __repr__(self):
        return f"<User {self.email} ({self.role})>"


class Donation(db.Model):
    __tablename__ = "donations"

    id = db.Column(db.Integer, primary_key=True)
    donor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    food_name = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    pickup_location = db.Column(db.String(255), nullable=False)
    available_until = db.Column(db.DateTime, nullable=False)
    description = db.Column(db.Text, nullable=True)
    image_filename = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(20), default="AVAILABLE", nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    donor = db.relationship("User", backref=db.backref("donations", lazy=True))

    def __repr__(self):
        return f"<Donation {self.id}: {self.food_name} ({self.status})>"


class Reservation(db.Model):
    __tablename__ = "reservations"

    id = db.Column(db.Integer, primary_key=True)
    donation_id = db.Column(db.Integer, db.ForeignKey("donations.id"), nullable=False, unique=True)
    ngo_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    reserved_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    pickup_status = db.Column(db.String(20), default="RESERVED", nullable=False)

    donation = db.relationship("Donation", backref=db.backref("reservation", uselist=False, lazy=True))
    ngo = db.relationship("User", backref=db.backref("reservations", lazy=True))

    def __repr__(self):
        return f"<Reservation {self.id}: Donation {self.donation_id} by NGO {self.ngo_id} ({self.pickup_status})>"


EMAIL_REGEX = r"^[\w\.-]+@[\w\.-]+\.\w+$"


def is_valid_email(email):
    return re.match(EMAIL_REGEX, email) is not None


def check_and_update_expired_donations():
    """
    Checks for any donations that are marked 'AVAILABLE' but whose
    'available_until' timestamp is in the past, and updates their status to 'EXPIRED'.
    Structured as a standalone reusable function to facilitate future extraction
    to an AWS Lambda function triggered by EventBridge Scheduler.
    """
    now = datetime.now(IST_TZ).replace(tzinfo=None)
    expired_donations = Donation.query.filter(
        Donation.status == "AVAILABLE",
        Donation.available_until < now,
    ).all()

    if expired_donations:
        for donation in expired_donations:
            donation.status = "EXPIRED"
        db.session.commit()
    return len(expired_donations)


def init_db(engine=None, seed_admin=False, admin_email=None, admin_password=None):
    """
    Initializes database tables.
    If engine is provided, creates tables on that engine directly.
    Optionally seeds a default admin account.
    """
    with app.app_context():
        if engine is not None:
            db.metadata.create_all(bind=engine)
        else:
            db.create_all()

        if seed_admin:
            seed_default_admin(admin_email=admin_email, admin_password=admin_password)


def seed_default_admin(admin_email=None, admin_password=None):
    """
    Seeds a default admin user if no admin user exists.
    In production / MySQL, requires an explicit password or ADMIN_DEFAULT_PASSWORD env var.
    """
    with app.app_context():
        admin_user = User.query.filter_by(role="admin").first()
        if admin_user:
            return admin_user

        email = admin_email or os.environ.get("ADMIN_DEFAULT_EMAIL", "admin@foodbridge.org")
        password = admin_password or os.environ.get("ADMIN_DEFAULT_PASSWORD")

        # If no password is provided in development SQLite mode, use a safe dev default
        if not password:
            if app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite"):
                password = "Admin@123"
            else:
                raise ValueError(
                    "Cannot seed admin in production without ADMIN_DEFAULT_PASSWORD environment variable or explicit password."
                )

        demo_admin = User(
            name="System Admin",
            email=email,
            password_hash=generate_password_hash(password),
            role="admin",
        )
        db.session.add(demo_admin)
        db.session.commit()
        return demo_admin


@app.cli.command("init-db")
def init_db_cli():
    """Create database tables without seeding admin."""
    init_db(seed_admin=False)
    print("Database tables initialized successfully.")


@app.cli.command("seed-admin")
def seed_admin_cli():
    """Seed the default admin account if none exists."""
    admin = seed_default_admin()
    if admin:
        print(f"Admin account confirmed: {admin.email}")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if "user_id" in session:
        return redirect_user_dashboard(session.get("user_role"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        role = request.form.get("role", "").strip().lower()

        # Validation
        if not name or not email or not password or not confirm_password or not role:
            flash("All fields are required.", "danger")
            return render_template("register.html", name=name, email=email, role=role)

        if not is_valid_email(email):
            flash("Please enter a valid email address.", "danger")
            return render_template("register.html", name=name, email=email, role=role)

        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return render_template("register.html", name=name, email=email, role=role)

        # Do NOT allow users to register themselves as Admin
        if role not in ["donor", "ngo"]:
            flash("Invalid role selected. Only Donor and NGO / Volunteer registrations are allowed.", "danger")
            return render_template("register.html", name=name, email=email, role=role)

        # Check for duplicate email
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash("An account with this email address already exists. Please log in.", "danger")
            return render_template("register.html", name=name, email=email, role=role)

        # Hash password and create user
        hashed_password = generate_password_hash(password)
        new_user = User(
            name=name,
            email=email,
            password_hash=hashed_password,
            role=role,
        )
        db.session.add(new_user)
        db.session.commit()

        flash("Registration successful! You can now log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect_user_dashboard(session.get("user_role"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not email or not password:
            flash("Please enter both email and password.", "danger")
            return render_template("login.html", email=email)

        user = User.query.filter_by(email=email).first()

        if not user or not check_password_hash(user.password_hash, password):
            flash("Invalid email or password.", "danger")
            return render_template("login.html", email=email)

        # Successful login: set session
        session.clear()
        session["user_id"] = user.id
        session["user_name"] = user.name
        session["user_email"] = user.email
        session["user_role"] = user.role

        return redirect_user_dashboard(user.role)

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been successfully logged out.", "info")
    return redirect(url_for("login"))


def redirect_user_dashboard(role):
    if role == "donor":
        return redirect(url_for("donor_dashboard"))
    elif role == "ngo":
        return redirect(url_for("ngo_dashboard"))
    elif role == "admin":
        return redirect(url_for("admin_dashboard"))
    return redirect(url_for("index"))


# Donor Routes
@app.route("/donor/dashboard")
def donor_dashboard():
    if "user_id" not in session:
        flash("Please log in to access your dashboard.", "warning")
        return redirect(url_for("login"))
    if session.get("user_role") != "donor":
        flash("Unauthorized access for this role.", "danger")
        return redirect_user_dashboard(session.get("user_role"))

    # Local development expiry check
    if not os.environ.get("USE_SECRETS_MANAGER"):
        check_and_update_expired_donations()

    donations = (
        Donation.query.filter_by(donor_id=session["user_id"])
        .order_by(Donation.created_at.desc())
        .all()
    )
    return render_template("donor_dashboard.html", donations=donations)


@app.route("/donor/donations/add", methods=["GET", "POST"])
def add_donation():
    if "user_id" not in session:
        flash("Please log in to access this page.", "warning")
        return redirect(url_for("login"))
    if session.get("user_role") != "donor":
        flash("Unauthorized access for this role.", "danger")
        return redirect_user_dashboard(session.get("user_role"))

    if request.method == "POST":
        food_name = request.form.get("food_name", "").strip()
        category = request.form.get("category", "").strip()
        quantity_raw = request.form.get("quantity", "").strip()
        pickup_location = request.form.get("pickup_location", "").strip()
        available_until_raw = request.form.get("available_until", "").strip()
        description = request.form.get("description", "").strip()
        image_file = request.files.get("food_image")

        errors = []
        if not food_name:
            errors.append("Food name is required.")
        if not category or category not in DONATION_CATEGORIES:
            errors.append("Please select a valid category.")

        quantity = None
        try:
            quantity = int(quantity_raw)
            if quantity <= 0:
                errors.append("Quantity must be greater than 0.")
        except (ValueError, TypeError):
            errors.append("Quantity must be a valid number greater than 0.")

        if not pickup_location:
            errors.append("Pickup location is required.")

        available_until = None
        if not available_until_raw:
            errors.append("Available until date and time is required.")
        else:
            try:
                available_until = datetime.fromisoformat(available_until_raw)
            except ValueError:
                errors.append("Invalid date and time for Available Until.")

        saved_filename = None
        if image_file and image_file.filename != "":
            is_valid, err_msg, content_type, file_bytes = validate_image_file(image_file)
            if not is_valid:
                errors.append(err_msg)
            else:
                safe_name = secure_filename(image_file.filename)
                unique_filename = f"{uuid.uuid4().hex[:10]}_{safe_name}"

                use_s3 = app.config.get("USE_S3", False) or os.environ.get("USE_S3", "").strip().lower() in ("true", "1", "yes")

                if use_s3:
                    bucket = app.config.get("S3_BUCKET") or os.environ.get("S3_BUCKET", "foodbridge-donations-879385476807-v2")
                    s3_key = f"donations/{unique_filename}"
                    try:
                        client = get_s3_client()
                        client.put_object(
                            Bucket=bucket,
                            Key=s3_key,
                            Body=file_bytes,
                            ContentType=content_type,
                            ServerSideEncryption="AES256",
                        )
                        saved_filename = unique_filename
                    except Exception as e:
                        app.logger.error(f"S3 image upload failed for key {s3_key}: {type(e).__name__}")
                        errors.append("Failed to upload image to secure cloud storage. Please try again.")
                else:
                    image_path = os.path.join(app.config["UPLOAD_FOLDER"], unique_filename)
                    with open(image_path, "wb") as f:
                        f.write(file_bytes)
                    saved_filename = unique_filename

        if errors:
            for err in errors:
                flash(err, "danger")
            return render_template(
                "add_donation.html",
                categories=DONATION_CATEGORIES,
                food_name=food_name,
                category=category,
                quantity=quantity_raw,
                pickup_location=pickup_location,
                available_until=available_until_raw,
                description=description,
            )

        new_donation = Donation(
            donor_id=session["user_id"],
            food_name=food_name,
            category=category,
            quantity=quantity,
            pickup_location=pickup_location,
            available_until=available_until,
            description=description or None,
            image_filename=saved_filename,
            status="AVAILABLE",
        )
        db.session.add(new_donation)
        db.session.commit()

        # Publish SNS Notification strictly AFTER successful DB commit
        publish_sns_notification("DONATION_CREATED", donation=new_donation)

        flash("Food donation added successfully.", "success")
        return redirect(url_for("donor_dashboard"))

    return render_template("add_donation.html", categories=DONATION_CATEGORIES)


# NGO Routes
@app.route("/ngo/dashboard")
def ngo_dashboard():
    if "user_id" not in session:
        flash("Please log in to access your dashboard.", "warning")
        return redirect(url_for("login"))
    if session.get("user_role") != "ngo":
        flash("Unauthorized access for this role.", "danger")
        return redirect_user_dashboard(session.get("user_role"))

    # Local development expiry check
    if not os.environ.get("USE_SECRETS_MANAGER"):
        check_and_update_expired_donations()

    # Get filter query parameters
    selected_category = request.args.get("category", "").strip()
    location_query = request.args.get("location", "").strip()

    if os.environ.get("USE_SECRETS_MANAGER"):
        query = Donation.query.filter(Donation.status == "AVAILABLE")
    else:
        now = datetime.now(IST_TZ).replace(tzinfo=None)
        query = Donation.query.filter(
            Donation.status == "AVAILABLE",
            Donation.available_until >= now,
        )

    if selected_category and selected_category in DONATION_CATEGORIES:
        query = query.filter(Donation.category == selected_category)

    if location_query:
        query = query.filter(Donation.pickup_location.ilike(f"%{location_query}%"))

    available_donations = query.order_by(Donation.created_at.desc()).all()
    my_reservations = (
        Reservation.query.filter_by(ngo_id=session["user_id"])
        .order_by(Reservation.reserved_at.desc())
        .all()
    )
    return render_template(
        "ngo_dashboard.html",
        available_donations=available_donations,
        my_reservations=my_reservations,
        categories=DONATION_CATEGORIES,
        selected_category=selected_category,
        location_query=location_query,
    )


@app.route("/ngo/donations/<int:donation_id>/reserve", methods=["POST"])
def reserve_donation(donation_id):
    if "user_id" not in session:
        flash("Please log in to reserve food donations.", "warning")
        return redirect(url_for("login"))
    if session.get("user_role") != "ngo":
        flash("Unauthorized access for this role.", "danger")
        return redirect_user_dashboard(session.get("user_role"))

    # Local development expiry check to ensure donation hasn't expired
    check_and_update_expired_donations()

    donation = Donation.query.get_or_404(donation_id)

    # Validate donation is still AVAILABLE
    if donation.status != "AVAILABLE":
        flash("This food donation is no longer available for reservation.", "danger")
        return redirect(url_for("ngo_dashboard"))

    # Validate donation does not already have an active reservation
    existing_reservation = Reservation.query.filter_by(donation_id=donation.id).first()
    if existing_reservation:
        flash("This food donation has already been reserved.", "danger")
        return redirect(url_for("ngo_dashboard"))

    # Create reservation and update donation status
    new_reservation = Reservation(
        donation_id=donation.id,
        ngo_id=session["user_id"],
        pickup_status="RESERVED",
    )
    donation.status = "RESERVED"
    db.session.add(new_reservation)
    db.session.commit()

    # Publish SNS Notification strictly AFTER successful DB commit
    ngo_user = db.session.get(User, session["user_id"])
    ngo_name = ngo_user.name if ngo_user else session.get("user_name", "An NGO Partner")
    publish_sns_notification("DONATION_RESERVED", donation=donation, ngo_name=ngo_name)

    flash("Food donation reserved successfully.", "success")
    return redirect(url_for("ngo_dashboard"))


@app.route("/ngo/reservations/<int:reservation_id>/complete", methods=["POST"])
def complete_reservation(reservation_id):
    if "user_id" not in session:
        flash("Please log in to manage reservations.", "warning")
        return redirect(url_for("login"))
    if session.get("user_role") != "ngo":
        flash("Unauthorized access for this role.", "danger")
        return redirect_user_dashboard(session.get("user_role"))

    reservation = Reservation.query.get_or_404(reservation_id)

    # Validate ownership: an NGO must not complete another NGO's reservation
    if reservation.ngo_id != session["user_id"]:
        flash("Unauthorized action: You cannot mark another organization's reservation as collected.", "danger")
        return redirect(url_for("ngo_dashboard"))

    if reservation.pickup_status == "COMPLETED":
        flash("This reservation has already been marked as collected.", "info")
        return redirect(url_for("ngo_dashboard"))

    reservation.pickup_status = "COMPLETED"
    reservation.donation.status = "COMPLETED"
    db.session.commit()

    # Publish SNS Notification strictly AFTER successful DB commit
    publish_sns_notification("DONATION_COLLECTED", donation=reservation.donation)

    flash("Food pickup completed successfully.", "success")
    return redirect(url_for("ngo_dashboard"))


@app.route("/admin/dashboard")
def admin_dashboard():
    if "user_id" not in session:
        flash("Please log in to access the admin dashboard.", "warning")
        return redirect(url_for("login"))
    if session.get("user_role") != "admin":
        flash("Unauthorized access for this role.", "danger")
        return redirect_user_dashboard(session.get("user_role"))

    # Local development expiry check
    if not os.environ.get("USE_SECRETS_MANAGER"):
        check_and_update_expired_donations()

    # Calculate statistics
    stats = {
        "total_users": User.query.count(),
        "total_donors": User.query.filter_by(role="donor").count(),
        "total_ngos": User.query.filter_by(role="ngo").count(),
        "total_donations": Donation.query.count(),
        "available_donations": Donation.query.filter_by(status="AVAILABLE").count(),
        "reserved_donations": Donation.query.filter_by(status="RESERVED").count(),
        "completed_donations": Donation.query.filter_by(status="COMPLETED").count(),
        "expired_donations": Donation.query.filter_by(status="EXPIRED").count(),
    }

    recent_donations = (
        Donation.query.order_by(Donation.created_at.desc()).limit(15).all()
    )
    recent_reservations = (
        Reservation.query.order_by(Reservation.reserved_at.desc()).limit(15).all()
    )

    return render_template(
        "admin_dashboard.html",
        stats=stats,
        recent_donations=recent_donations,
        recent_reservations=recent_reservations,
    )


if __name__ == "__main__":
    # In direct local development execution, ensure database and dev admin are present
    with app.app_context():
        init_db(seed_admin=True)
    port = int(os.environ.get("PORT", 5001))
    app.run(debug=True, host="127.0.0.1", port=port)
