import boto3
from botocore.exceptions import ClientError

REGION = "ap-south-1"
BACKUP_TOPIC = "arn:aws:sns:ap-south-1:879385476807:BackupStatusTopic"
HYPOTHETICAL_TOPIC = "arn:aws:sns:ap-south-1:879385476807:foodbridge-notifications"

print("==================================================")
print("TASK 3: SNS Permissions & Resource Audit on EC2")
print("==================================================")

sns = boto3.client("sns", region_name=REGION)
sts = boto3.client("sts", region_name=REGION)

caller = sts.get_caller_identity()
print(f"Caller Identity: {caller.get('Arn')}")

# 1. Test ListTopics from EC2
print("\n[CHECK 1] Testing sns:ListTopics from EC2 role...")
try:
    resp = sns.list_topics()
    topics = resp.get("Topics", [])
    print(f"  [PASS] sns:ListTopics succeeded! Found {len(topics)} topic(s):")
    for t in topics:
        print(f"    - {t.get('TopicArn')}")
except ClientError as e:
    err_code = e.response.get("Error", {}).get("Code")
    print(f"  [FAIL] sns:ListTopics failed: {err_code} - {e.response.get('Error', {}).get('Message')}")

# 2. Test GetTopicAttributes on existing topic
print("\n[CHECK 2] Testing sns:GetTopicAttributes on existing topic...")
try:
    attr = sns.get_topic_attributes(TopicArn=BACKUP_TOPIC)
    print(f"  [PASS] sns:GetTopicAttributes succeeded on {BACKUP_TOPIC}")
except ClientError as e:
    err_code = e.response.get("Error", {}).get("Code")
    print(f"  [INFO] sns:GetTopicAttributes on {BACKUP_TOPIC}: {err_code}")

# 3. Test publish simulation on hypothetical FoodBridge topic
# (Testing with an invalid ARN or probe to see if permission is denied or topic doesn't exist)
print("\n[CHECK 3] Probing sns:Publish permissions on foodbridge-notifications...")
try:
    # A dry probe: If permission is denied by IAM, AWS returns AuthorizationError before checking if topic exists!
    # If IAM allows sns:Publish on the ARN, AWS will return NotFound / InvalidParameter.
    sns.publish(
        TopicArn=HYPOTHETICAL_TOPIC,
        Message="Test probe",
        Subject="Probe"
    )
    print("  [WARN] Unexpected: Publish succeeded to hypothetical topic!")
except ClientError as e:
    err_code = e.response.get("Error", {}).get("Code")
    msg = e.response.get("Error", {}).get("Message")
    print(f"  IAM Evaluation Result:")
    print(f"    Code: {err_code}")
    print(f"    Message: {msg}")
    if err_code in ["AuthorizationError", "AccessDenied"]:
        print(f"  [CONFIRMED] EC2 role does NOT have sns:Publish permission for {HYPOTHETICAL_TOPIC} yet.")
    elif err_code == "NotFound":
        print(f"  [CONFIRMED] EC2 role IS authorized by IAM for sns:Publish (returned NotFound since topic doesn't exist yet).")

print("\n==================================================")
