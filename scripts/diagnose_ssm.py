#!/usr/bin/env python3
"""
Step 19C SSM Agent Read-Only Connectivity Diagnostics
Gathers all facts without modifying any services, packages, or files.
"""
import os
import socket
import subprocess
import sys
import urllib.request
import json

def run_cmd(cmd):
    try:
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        return res.returncode, res.stdout.strip(), res.stderr.strip()
    except Exception as e:
        return -1, "", str(e)

def main():
    print("=" * 70)
    print("STEP 19C — READ-ONLY SSM AGENT CONNECTIVITY DIAGNOSIS")
    print("=" * 70)

    # 1. Check Package Installation
    print("\n[1] Checking SSM Agent Installation:")
    code, out, err = run_cmd("snap list amazon-ssm-agent")
    if code == 0:
        print(f"    Snap Package: INSTALLED\n    {out}")
    else:
        print(f"    Snap Package: NOT FOUND ({err or out})")

    code, out, err = run_cmd("dpkg -l | grep -i ssm")
    if code == 0 and out:
        print(f"    DEB Package: INSTALLED\n    {out}")
    else:
        print("    DEB Package: NOT FOUND")

    code, out, _ = run_cmd("which amazon-ssm-agent")
    print(f"    Binary location: {out or 'None found'}")

    # 2. Check Service Status & Running Process
    print("\n[2] Checking SSM Agent Service Status:")
    for svc in ["snap.amazon-ssm-agent.amazon-ssm-agent.service", "amazon-ssm-agent.service"]:
        code, out, _ = run_cmd(f"systemctl is-active {svc}")
        code_en, out_en, _ = run_cmd(f"systemctl is-enabled {svc}")
        print(f"    Service {svc}:")
        print(f"      Active: {out} | Enabled: {out_en}")

    code, out, _ = run_cmd("ps aux | grep -i '[a]mazon-ssm-agent'")
    print(f"    Running Processes:\n      {out or 'No running amazon-ssm-agent process found'}")

    # 3. Check Network Connectivity to Regional Endpoints (HTTPS Port 443)
    print("\n[3] Testing Connectivity to Regional SSM Endpoints (ap-south-1:443):")
    endpoints = [
        "ssm.ap-south-1.amazonaws.com",
        "ssmmessages.ap-south-1.amazonaws.com",
        "ec2messages.ap-south-1.amazonaws.com",
    ]
    for ep in endpoints:
        try:
            s = socket.create_connection((ep, 443), timeout=5)
            s.close()
            print(f"    [OK] Reachable: {ep}:443")
        except Exception as e:
            print(f"    [FAIL] Unreachable: {ep}:443 - {e}")

    # 4. Check Instance Metadata (IMDSv2) & IAM Role Availability
    print("\n[4] Checking Instance Metadata Service (IMDSv2):")
    try:
        # Get token
        token_req = urllib.request.Request(
            "http://169.254.169.254/latest/api/token",
            method="PUT",
            headers={"X-aws-ec2-metadata-token-ttl-seconds": "21600"}
        )
        with urllib.request.urlopen(token_req, timeout=3) as resp:
            token = resp.read().decode()

        # Query IAM info
        iam_req = urllib.request.Request(
            "http://169.254.169.254/latest/meta-data/iam/info",
            headers={"X-aws-ec2-metadata-token": token}
        )
        with urllib.request.urlopen(iam_req, timeout=3) as resp:
            iam_info = json.loads(resp.read().decode())
            print(f"    IMDSv2 Status: REACHABLE")
            print(f"    InstanceProfileArn: {iam_info.get('InstanceProfileArn')}")
            print(f"    InstanceProfileId:  {iam_info.get('InstanceProfileId')}")

        # Query security credentials role name (without logging secrets!)
        role_req = urllib.request.Request(
            "http://169.254.169.254/latest/meta-data/iam/security-credentials/",
            headers={"X-aws-ec2-metadata-token": token}
        )
        with urllib.request.urlopen(role_req, timeout=3) as resp:
            role_name = resp.read().decode().strip()
            print(f"    IAM Role Name:      {role_name}")

        # Verify credential expiration time without exposing keys
        cred_req = urllib.request.Request(
            f"http://169.254.169.254/latest/meta-data/iam/security-credentials/{role_name}",
            headers={"X-aws-ec2-metadata-token": token}
        )
        with urllib.request.urlopen(cred_req, timeout=3) as resp:
            cred_info = json.loads(resp.read().decode())
            code_status = cred_info.get("Code")
            expiration = cred_info.get("Expiration")
            last_updated = cred_info.get("LastUpdated")
            print(f"    Credentials Status: {code_status}")
            print(f"    Last Updated:       {last_updated}")
            print(f"    Expiration:         {expiration}")
            print(f"    Access Key Present: {'Yes' if cred_info.get('AccessKeyId') else 'No'}")
    except Exception as e:
        print(f"    IMDSv2 Error: {e}")

    # 5. Inspect Recent SSM Agent Logs
    print("\n[5] Inspecting SSM Agent Logs:")
    log_paths = [
        "/var/log/amazon/ssm/amazon-ssm-agent.log",
        "/var/log/amazon/ssm/errors.log",
    ]
    for lp in log_paths:
        if os.path.exists(lp):
            print(f"    Log File Found: {lp}")
            code, out, _ = run_cmd(f"tail -n 25 {lp}")
            print(f"--- Last 25 lines of {lp} ---")
            print(out)
            print("-" * 50)
        else:
            print(f"    Log File Not Found: {lp}")

    # Journal logs
    print("\n[6] Inspecting Recent Systemd Journal for SSM Agent:")
    code, out, _ = run_cmd("journalctl -u snap.amazon-ssm-agent.amazon-ssm-agent.service -n 30 --no-pager")
    if code == 0 and out and "No entries" not in out:
        print("--- Last 30 lines of journalctl (snap) ---")
        print(out)
        print("-" * 50)
    else:
        code2, out2, _ = run_cmd("journalctl -u amazon-ssm-agent.service -n 30 --no-pager")
        if code2 == 0 and out2 and "No entries" not in out2:
            print("--- Last 30 lines of journalctl (systemd) ---")
            print(out2)
            print("-" * 50)
        else:
            print("    No journal entries found for SSM agent services.")

    print("\n" + "=" * 70)
    print("DIAGNOSIS COLLECTION COMPLETE")
    print("=" * 70)

if __name__ == "__main__":
    main()
