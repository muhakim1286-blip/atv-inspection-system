# ☁️ AWS DEPLOYMENT GUIDE - ATV INSPECTION SYSTEM

## Overview
Deploy the ATV Inspection system to AWS for enterprise-grade reliability, auto-scaling, and global distribution.

**Cost:** $45-115/month (after free tier)  
**Setup Time:** 2-3 hours  
**Uptime SLA:** 99.99%

---

## Architecture

```
Users
  ↓
Route 53 (DNS)
  ↓
CloudFront (CDN)
  ↓
Elastic Load Balancer (ALB)
  ↓
Auto Scaling Group (EC2 instances)
  ├─ EC2 #1 (Backend)
  ├─ EC2 #2 (Backend)
  └─ Scales 1-10 based on load
  ↓
RDS PostgreSQL (Database with Multi-AZ)
  ↓
S3 Bucket (Photo Storage with Cross-Region Replication)
```

---

## Prerequisites

1. **AWS Account** (create at aws.amazon.com)
2. **Your Files:**
   - `GY6-Daily-Routine-Check-v2.html`
   - `Admin-Dashboard-Professional.html`
   - `backend_main.py`
   - `requirements.txt`
3. **GitHub Account** (for code repository)
4. **AWS CLI** installed (optional but recommended)

---

## Step 1: Set Up AWS Account & IAM (30 minutes)

### 1.1 Create AWS Account
```
1. Go to aws.amazon.com
2. Click "Create an AWS Account"
3. Fill in email, password, account name
4. Complete identity verification
5. Choose support plan (Free tier is fine)
```

### 1.2 Set Up IAM User
```
1. AWS Console → IAM → Users
2. Click "Create user"
3. Username: atv-inspection-admin
4. Attach policies:
   - EC2FullAccess
   - RDSFullAccess
   - S3FullAccess
   - CloudFrontFullAccess
   - IAMReadOnlyAccess
5. Create access key (for AWS CLI)
```

### 1.3 Configure Billing Alerts
```
1. AWS Console → Billing → Budgets
2. Create budget: $200/month
3. Alert at 80% usage
4. You'll receive email if spending approaches $160
```

---

## Step 2: Deploy Backend to EC2 (30 minutes)

### 2.1 Create EC2 Instance

```
1. AWS Console → EC2 → Instances
2. Click "Launch Instance"

3. Choose AMI: Ubuntu 22.04 LTS
4. Instance Type: t3.small (or t2.micro for testing)
   • vCPU: 2
   • Memory: 2GB
   • Estimated cost: $0.02/hour = ~$15/month

5. Configure instance details:
   • Network: Default VPC
   • Auto-assign Public IP: Enable
   • IAM Role: atv-inspection-admin

6. Storage: 20GB (default is fine)

7. Tags:
   • Name: atv-backend-server
   • Environment: production

8. Security Group: Create new
   • Name: atv-backend-sg
   • Inbound rules:
     ✓ SSH (port 22) - from your IP only
     ✓ HTTP (port 80) - from anywhere (0.0.0.0/0)
     ✓ HTTPS (port 443) - from anywhere
     ✓ Custom TCP (port 8000) - from anywhere
   • Outbound: All traffic

9. Review & Launch
10. Create new key pair: atv-inspection-key
    • Download .pem file
    • Keep safe (don't lose this!)

11. Launch Instance
12. Wait 2-3 minutes for startup
```

### 2.2 Connect to EC2 Instance

```bash
# From your computer (Terminal/Command Prompt)
chmod 600 atv-inspection-key.pem
ssh -i atv-inspection-key.pem ubuntu@<Your-EC2-Public-IP>
```

### 2.3 Install Dependencies

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python & pip
sudo apt install python3 python3-pip -y

# Install other dependencies
sudo apt install git curl wget -y

# Create app directory
mkdir -p /home/ubuntu/app
cd /home/ubuntu/app

# Clone your GitHub repo or upload files
# Option A: Git clone (if you have backend on GitHub)
git clone https://github.com/yourusername/atv-inspection-backend.git
cd atv-inspection-backend

# Option B: Upload files directly
# Use SCP to upload: scp -i atv-inspection-key.pem backend_main.py ubuntu@IP:/home/ubuntu/app/
```

### 2.4 Install Python Requirements

```bash
cd /home/ubuntu/app
sudo pip3 install -r requirements.txt
```

### 2.5 Create Systemd Service

```bash
sudo nano /etc/systemd/system/atv-backend.service
```

Paste this:
```
[Unit]
Description=ATV Inspection Backend API
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/app
ExecStart=/usr/bin/python3 /home/ubuntu/app/backend_main.py
Restart=on-failure
RestartSec=10
StandardOutput=inherit
StandardError=inherit
Environment="PORT=8000"

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable atv-backend.service
sudo systemctl start atv-backend.service
sudo systemctl status atv-backend.service
```

### 2.6 Get Your EC2 Public IP

```
AWS Console → EC2 → Instances
Copy "Public IPv4 address" of your instance
Example: 52.221.42.123

Your API is now at: http://52.221.42.123:8000
```

---

## Step 3: Set Up RDS Database (20 minutes)

### 3.1 Create RDS Instance

```
1. AWS Console → RDS → Databases
2. Click "Create database"

3. Engine: PostgreSQL (version 14 or higher)

4. Templates: Free tier
   (If not eligible, choose "Single Zone")

5. DB Instance Identifier: atv-inspection-db

6. Credentials:
   • Master username: postgres
   • Password: [create strong password]
   • Save this in secure location!

7. DB Instance Class: db.t3.micro (free tier) or db.t3.small

8. Storage:
   • Allocated storage: 20GB
   • Storage type: gp3 (default)
   • Enable auto-scaling: Yes (max 100GB)

9. Availability & Durability:
   • Multi-AZ deployment: Yes (for production)
   • Estimated cost: +$50/month for standby

10. Connectivity:
    • VPC: Default VPC
    • Public accessibility: Yes
    • VPC security group: Create new
    • Security group name: atv-db-sg

11. Database options:
    • DB name: atv_inspection
    • Backup retention: 30 days
    • Enable encryption: Yes
    • Enable monitoring: Yes

12. Create Database
13. Wait 5-10 minutes for creation
```

### 3.2 Get Connection String

```
1. AWS Console → RDS → Databases
2. Click your database name
3. Under "Connectivity & security", find:
   • Endpoint: atv-inspection-db.xxxxx.amazonaws.com
   • Port: 5432

Connection string format:
postgresql://postgres:PASSWORD@atv-inspection-db.xxxxx.amazonaws.com:5432/atv_inspection
```

### 3.3 Update Backend Configuration

```bash
ssh -i atv-inspection-key.pem ubuntu@<EC2-IP>
cd /home/ubuntu/app

# Edit backend_main.py
nano backend_main.py

# Find: DATABASE_URL = os.environ.get(...)
# Update to your RDS connection string
# Or set as environment variable:

export DATABASE_URL="postgresql://postgres:password@endpoint:5432/atv_inspection"

# Restart service
sudo systemctl restart atv-backend.service
```

---

## Step 4: Set Up S3 for Photo Storage (20 minutes)

### 4.1 Create S3 Bucket

```
1. AWS Console → S3
2. Click "Create bucket"

3. Bucket name: atv-inspection-photos-<random>
   (Must be globally unique)

4. Region: ap-southeast-1 (Singapore, closest to Malaysia)

5. Block Public Access: Uncheck "Block all public access"
   (Photos need to be accessible)

6. Enable versioning: Yes (for backup)

7. Enable encryption: Yes (AES-256)

8. Create bucket
```

### 4.2 Configure Bucket Policy

```
1. Click your bucket
2. Click "Permissions" tab
3. Scroll to "Bucket policy"
4. Click "Edit"

Paste this policy:
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "PublicRead",
      "Effect": "Allow",
      "Principal": "*",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::atv-inspection-photos-*/*"
    },
    {
      "Sid": "AllowBackendUpload",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::YOUR-ACCOUNT-ID:user/atv-inspection-admin"
      },
      "Action": ["s3:PutObject", "s3:DeleteObject"],
      "Resource": "arn:aws:s3:::atv-inspection-photos-*/*"
    }
  ]
}
```

### 4.3 Enable Cross-Region Replication

```
1. Click your bucket
2. Click "Management" tab
3. Scroll to "Replication rules"
4. Create rule:
   • Destination: Create new bucket (same region for now)
   • Enable: Yes
5. This automatically backs up photos
```

### 4.4 Configure Backend for S3

```bash
# Install boto3 (AWS SDK for Python)
sudo pip3 install boto3

# Update backend_main.py to use S3
# Add to requirements.txt:
boto3>=1.26.0
```

---

## Step 5: Deploy Frontend to S3 + CloudFront (20 minutes)

### 5.1 Create Frontend Bucket

```
1. AWS Console → S3
2. Click "Create bucket"

3. Bucket name: atv-inspection-frontend-<random>

4. Region: ap-southeast-1

5. Block Public Access: Uncheck all

6. Enable versioning: Yes

7. Create bucket
```

### 5.2 Upload Frontend Files

```
1. Click your frontend bucket
2. Click "Upload"
3. Drag & drop:
   • GY6-Daily-Routine-Check-v2.html
   • Admin-Dashboard-Professional.html
4. Click "Upload"
```

### 5.3 Create CloudFront Distribution

```
1. AWS Console → CloudFront
2. Click "Create distribution"

3. Origin domain: Select your frontend S3 bucket

4. Origin Access: Create OAI
   • This allows CloudFront to read from S3

5. Viewer protocol policy: Redirect HTTP to HTTPS

6. Default root object: 
   • Leave blank (files accessed by full path)

7. Cache settings:
   • TTL: 3600 seconds (1 hour)
   • Compress objects: Yes

8. Create distribution
9. Wait 5-10 minutes for deployment

Your CDN URL will be: d1234567890.cloudfront.net
```

### 5.4 Update Frontend Code

Now update your HTML files to point to:
- EC2 Backend: `http://52.221.42.123:8000` (or elastic IP)
- S3 Frontend: `https://d1234567890.cloudfront.net`

---

## Step 6: Set Up Auto-Scaling (20 minutes)

### 6.1 Create Launch Template

```
1. AWS Console → EC2 → Launch Templates
2. Click "Create launch template"

3. Template name: atv-backend-template

4. Amazon Machine Image: Ubuntu 22.04 LTS

5. Instance type: t3.small

6. Key pair: atv-inspection-key

7. Security group: atv-backend-sg

8. User data (script to run on startup):
```

Paste this in User Data:
```bash
#!/bin/bash
cd /home/ubuntu/app
source /home/ubuntu/app/venv/bin/activate
export DATABASE_URL="your-rds-connection-string"
python3 /home/ubuntu/app/backend_main.py
```

### 6.2 Create Auto Scaling Group

```
1. AWS Console → EC2 → Auto Scaling Groups
2. Click "Create Auto Scaling group"

3. Name: atv-backend-asg

4. Launch template: atv-backend-template

5. VPC: Default

6. Subnets: Select 2-3 subnets (for high availability)

7. Load balancer: Create Application Load Balancer
   • Name: atv-backend-alb
   • Scheme: Internet-facing
   • Listeners: HTTP on 80, HTTPS on 443

8. Group size:
   • Minimum: 1
   • Desired: 2
   • Maximum: 10

9. Scaling policies:
   • Scale up: CPU > 70%
   • Scale down: CPU < 30%

10. Create Auto Scaling group
```

Your system now auto-scales!

---

## Step 7: Set Up Route 53 (DNS) (15 minutes)

### 7.1 Register Domain (Optional)

```
If you want your own domain:
1. AWS Console → Route 53
2. Registered domains
3. Register new domain or transfer existing

If you use existing domain registrar, skip to 7.2
```

### 7.2 Create Hosted Zone

```
1. AWS Console → Route 53
2. Hosted zones
3. Create hosted zone
4. Domain name: yourdomain.com
5. Type: Public
6. Create hosted zone
```

### 7.3 Create Records

```
For CloudFront distribution:
1. Type: A (IPv4)
2. Name: yourdomain.com
3. Alias: Enable
4. Target: Your CloudFront distribution
5. Create record

For API backend (via ALB):
1. Type: A
2. Name: api.yourdomain.com
3. Alias: Enable
4. Target: Your ALB
5. Create record
```

Now your URLs will be:
- Dashboard: `https://yourdomain.com/Admin-Dashboard-Professional.html`
- API: `https://api.yourdomain.com`

---

## Step 8: Test Everything (20 minutes)

### 8.1 Test API Health

```bash
curl http://YOUR-EC2-IP:8000/api/health
# Should return: {"status": "ok"}
```

### 8.2 Test Form Submission

1. Open your frontend URL
2. Fill in test inspection
3. Submit form
4. Check if data appears in dashboard

### 8.3 Monitor in CloudWatch

```
1. AWS Console → CloudWatch
2. Check:
   • EC2 CPU utilization
   • RDS database connections
   • S3 upload volume
   • CloudFront requests
```

---

## Step 9: Set Up SSL/HTTPS (15 minutes)

### 9.1 Request SSL Certificate

```
1. AWS Console → Certificate Manager
2. Request certificate
3. Domain: yourdomain.com, *.yourdomain.com
4. Validation: DNS
5. Follow DNS validation steps
6. Certificate gets issued (5-10 min)
```

### 9.2 Update ALB Listener

```
1. AWS Console → Load Balancers
2. Click your ALB
3. Listeners:
   • HTTP:80 → Redirect to HTTPS
   • HTTPS:443 → Backend instances
4. Certificate: Your ACM certificate
5. Save
```

---

## Monitoring & Alerts (10 minutes)

### 10.1 Set Up Alarms

```
1. AWS Console → CloudWatch → Alarms
2. Create alarms for:
   • EC2 CPU > 80% (scale up)
   • EC2 CPU < 20% (scale down)
   • RDS CPU > 80%
   • RDS storage > 80%
   • ALB unhealthy hosts
```

### 10.2 Email Notifications

```
1. Create SNS topic: atv-alerts
2. Subscribe: your email
3. Link CloudWatch alarms to SNS
4. You'll get emails for issues
```

---

## Cost Estimation

| Service | Type | Estimated Cost |
|---------|------|---|
| EC2 | t3.small (1 instance) | $15/month |
| EC2 | Auto-scaling (0-10 instances) | +$5-50/month |
| RDS | db.t3.micro | $20/month |
| RDS | Multi-AZ standby | +$20/month |
| S3 | Storage (100GB photos) | $2/month |
| S3 | Data transfer | +$5/month |
| CloudFront | CDN delivery | +$10/month |
| Route 53 | Hosted zone | $0.50/month |
| Load Balancer | ALB | $15/month |
| **TOTAL** | | **$45-115/month** |

---

## Scaling Guide

### If experiencing slowness:

1. **Check EC2 CPU** → CPU > 80% = add instance (auto-scaling does this)
2. **Check database** → RDS queries slow = upgrade to larger instance
3. **Check CloudFront** → Cache might be stale = invalidate cache
4. **Check S3** → Transfer limit reached = request limit increase

### Expected capacity:

- **Free tier (t2.micro):** 100 inspections/day
- **t3.small:** 500 inspections/day
- **t3.medium:** 2000 inspections/day
- **t3.large:** 5000+ inspections/day

---

## Troubleshooting

**Backend not responding:**
- Check EC2 security group (port 8000 open?)
- Check backend logs: `sudo systemctl logs atv-backend`
- Check RDS connection in logs

**Photos not uploading:**
- Check S3 bucket policy
- Check IAM user permissions
- Check S3 bucket region

**Database connection fails:**
- Check RDS security group
- Check connection string in backend
- Test connection: `psql postgresql://...`

**High costs:**
- Check data transfer (maybe reduce CloudFront TTL)
- Check EC2 instance type (maybe smaller is fine)
- Check RDS storage (enable auto-cleanup)

---

## Next Steps

1. **Monitor for 1 month** - See real usage patterns
2. **Optimize costs** - Adjust instance types based on actual usage
3. **Add monitoring dashboard** - CloudWatch dashboard with metrics
4. **Setup backups** - Automated RDS snapshots to S3
5. **Plan for growth** - Multi-region if going global

---

You're ready to deploy! AWS provides enterprise-grade infrastructure with excellent scaling and reliability.
