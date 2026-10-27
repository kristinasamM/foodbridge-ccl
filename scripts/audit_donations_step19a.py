#!/usr/bin/env python3
"""
Step 19A Read-Only Donation Expiration Inspection
Inspects the MySQL donations table without making any modifications.
"""
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, "/var/www/foodbridge")

env_file = "/var/www/foodbridge/.env"
if os.path.exists(env_file):
    with open(env_file, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip()

from app import app, db, Donation, Reservation

def main():
    print("=" * 70)
    print("STEP 19A — READ-ONLY DONATION EXPIRATION INSPECTION")
    print("=" * 70)
    
    with app.app_context():
        now_utc = datetime.now(timezone.utc)
        now_naive = datetime.now()
        now_db = db.session.execute(db.text("SELECT NOW(), UTC_TIMESTAMP()")).fetchone()
        
        print(f"Current EC2 system time (naive): {now_naive}")
        print(f"Current EC2 UTC time:            {now_utc}")
        print(f"Current MySQL NOW():             {now_db[0]}")
        print(f"Current MySQL UTC_TIMESTAMP():   {now_db[1]}")
        print("-" * 70)
        
        donations = Donation.query.order_by(Donation.id).all()
        print(f"Total donations in MySQL: {len(donations)}")
        print(f"{'ID':<4} | {'Status':<10} | {'Available Until':<20} | {'Passed?':<8} | {'Food Name':<25}")
        print("-" * 70)
        
        available_expired_count = 0
        for d in donations:
            has_passed = False
            if d.available_until:
                # Compare against both naive and DB time
                has_passed = d.available_until < now_naive
            
            is_available = (d.status == "AVAILABLE")
            if is_available and has_passed:
                available_expired_count += 1
                
            flag = "YES" if has_passed else "NO"
            print(f"{d.id:<4} | {d.status:<10} | {str(d.available_until):<20} | {flag:<8} | {d.food_name[:25]:<25}")
            
        print("-" * 70)
        print(f"Total AVAILABLE donations that have passed available_until: {available_expired_count}")
        
        # Also inspect reservations
        print("\nReservations Check:")
        reservations = Reservation.query.all()
        print(f"Total reservations: {len(reservations)}")
        for r in reservations:
            print(f"  Reservation #{r.id}: Donation #{r.donation_id} | Status: {r.pickup_status} | NGO ID: {r.ngo_id}")
            
    print("=" * 70)

if __name__ == "__main__":
    main()
