# Cloud Resume Challenge

An implementation of the [Cloud Resume Challenge](https://cloudresumechallenge.dev/) on AWS using **AWS SAM** and **Python**.

## Architecture

```
Browser
  │
  │  (static site)
  ▼
CloudFront ──► S3 (HTML / CSS / JS)
  │
  │  (visitor counter: fetch GET)
  ▼
API Gateway ──► Lambda (Python) ──► DynamoDB
```

- **Frontend:** HTML resume styled with CSS, hosted on S3, served over HTTPS via CloudFront.
- **Visitor counter:** JavaScript on the page calls an HTTP API that increments and returns a count.
- **Backend:** API Gateway → Lambda (Python) → DynamoDB table storing the visit count.
- **IaC:** AWS SAM (`template.yaml`) defines the backend resources.
- **CI/CD:** GitHub Actions (to be added) deploys on push.

## Project structure

```
ResumeChallenge/
├── template.yaml              # SAM template (DynamoDB, Lambda, API Gateway)
├── samconfig.toml             # SAM deploy config
├── frontend/
│   ├── index.html             # the resume
│   ├── css/styles.css
│   └── js/counter.js          # calls the visitor-counter API
├── backend/
│   ├── visitor_counter/
│   │   ├── app.py             # Lambda handler
│   │   └── requirements.txt
│   └── tests/
│       └── test_app.py        # pytest for the Lambda
└── .github/workflows/
    └── deploy.yml             # CI/CD (to be added)
```

## Prerequisites

- AWS CLI configured (profile: `administrator`, region: `us-east-1`)
- AWS SAM CLI
- Python 3.13
- Docker (for `sam build --use-container` and local invokes)

## Backend: build, test, deploy

```powershell
# Run unit tests
pip install -r backend/visitor_counter/requirements.txt pytest boto3 moto
pytest backend/tests -v

# Validate the SAM template
sam validate --profile administrator

# Build
sam build

# Deploy (guided the first time)
sam deploy --guided --profile administrator
```

## Frontend

`frontend/js/counter.js` reads the API URL from `window.API_URL`. After deploying
the backend, set that value (the API Gateway invoke URL from the stack outputs)
in `index.html`, then upload the `frontend/` contents to S3.

### Hosting (S3 + CloudFront)

Infrastructure is defined in `frontend-infra.yaml` (private S3 bucket + CloudFront
with Origin Access Control, HTTPS enforced).

```powershell
# Deploy / update the hosting stack
aws cloudformation deploy --template-file frontend-infra.yaml `
  --stack-name cloud-resume-frontend --region us-east-1 --profile administrator

# Upload site files (bucket name is a stack output)
$bucket = "cloud-resume-frontend-site-369506522111"
aws s3 sync frontend/ "s3://$bucket/" --profile administrator --exclude "index.html" --cache-control "public, max-age=86400"
aws s3 cp frontend/index.html "s3://$bucket/index.html" --profile administrator --content-type "text/html; charset=utf-8" --cache-control "public, max-age=300"

# Invalidate the CloudFront cache so changes show immediately
aws cloudfront create-invalidation --distribution-id E1PVM3ISBGPOYT --paths "/*" --profile administrator
```

Live site: https://d3hf5icvswiyu1.cloudfront.net

## Status

- [x] Project scaffold
- [x] Frontend (placeholder resume + counter)
- [x] Backend (DynamoDB + Lambda + API Gateway + tests)
- [x] Deploy backend (stack: `cloud-resume-challenge`, API: `https://ukydqegjbd.execute-api.us-east-1.amazonaws.com/count`)
- [x] Host frontend on S3 + CloudFront (stack: `cloud-resume-frontend`, site: `https://d3hf5icvswiyu1.cloudfront.net`)
- [ ] Custom domain (Route 53 + ACM)
- [ ] CI/CD with GitHub Actions
