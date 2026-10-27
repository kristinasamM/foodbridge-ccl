#!/usr/bin/env python3
"""
Test whether FoodBridge-EC2-App-Role has AmazonSSMManagedInstanceCore permissions
using an action included in the policy: ssm:GetDocument
"""
import boto3

session = boto3.Session(region_name="ap-south-1")
ssm = session.client("ssm")

print("Testing ssm:GetDocument(Name='AWS-RunShellScript')...")
try:
    doc = ssm.get_document(Name="AWS-RunShellScript")
    print("SUCCESS: AmazonSSMManagedInstanceCore is active on FoodBridge-EC2-App-Role!")
    print("  Document Name:", doc.get("Name"))
    print("  Document Type:", doc.get("DocumentType"))
    print("  Document Version:", doc.get("DocumentVersion"))
except Exception as e:
    print("FAILED: Cannot get document:", type(e).__name__, "-", e)

print("\nTesting ssm:ListAssociations()...")
try:
    assoc = ssm.list_associations(AssociationFilterList=[{'key': 'InstanceId', 'value': 'i-01d9b606fb86b2dbd'}])
    print("SUCCESS: ssm:ListAssociations succeeded!")
except Exception as e:
    print("FAILED: ssm:ListAssociations:", type(e).__name__, "-", e)
