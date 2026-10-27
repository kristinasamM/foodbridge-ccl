#!/usr/bin/env python3
"""
Test whether EC2 IAM credentials can call SSM APIs
"""
import boto3

session = boto3.Session(region_name="ap-south-1")
sts = session.client("sts")
identity = sts.get_caller_identity()
print("STS Caller Identity:")
print("  Account:", identity.get("Account"))
print("  Arn:    ", identity.get("Arn"))
print("  UserId: ", identity.get("UserId"))

ssm = session.client("ssm")
try:
    resp = ssm.describe_instance_information()
    print("\nSSM describe_instance_information SUCCESS:")
    print("  Instances found:", len(resp.get("InstanceInformationList", [])))
    for inst in resp.get("InstanceInformationList", []):
        print("  - InstanceId:", inst.get("InstanceId"), "PingStatus:", inst.get("PingStatus"))
except Exception as e:
    print("\nSSM describe_instance_information Result:")
    print("  Error:", type(e).__name__, "-", e)
