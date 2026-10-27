# Cloud Resume Challenge — Full Walkthrough

A plain-English explanation of everything built in this project: what each piece
is, why it exists, and how it works together. Read top to bottom the first time.

---

## 1. The big picture

The goal: put an HTML resume on the internet, over HTTPS, with a visitor counter
that remembers how many times the page has been viewed. Everything is built on
AWS and defined as code so it's reproducible.

Here's the whole system in one diagram:

```
                    ┌─────────────────────────────────────────┐
   Your browser     │                  AWS                      │
   ───────────►     │                                           │
   https://...      │   CloudFront  ──(reads)──►  S3 bucket      │
   cloudfront.net   │   (CDN, HTTPS)              (HTML/CSS/JS)  │
        │           │                                           │
        │ page loads, JS runs                                   │
        │           │                                           │
        │ fetch()   │                                           │
        └──────────►│   API Gateway ──► Lambda ──► DynamoDB      │
   GET /count       │   (HTTP API)      (Python)   (the count)   │
                    │                                           │
                    └─────────────────────────────────────────┘
```

Two independent halves:

- **Frontend (the website):** the files a browser downloads — `index.html`,
  `styles.css`, `counter.js`. Stored in S3, delivered by CloudFront.
- **Backend (the counter):** a tiny program that adds 1 to a number in a database
  and returns it. Made of API Gateway + Lambda + DynamoDB.

They're deployed as two separate CloudFormation stacks so you can change one
without touching the other.

---

## 2. Prerequisites and account setup

### 2.1 AWS CLI and profiles

The **AWS CLI** is a command-line tool that talks to AWS. To use it, it needs
**credentials** that prove who you are. Credentials are organized into **profiles**
— named sets of settings stored on your computer in two files:

- `C:\Users\<you>\.aws\config` — non-secret settings (region, output format)
- `C:\Users\<you>\.aws\credentials` — the secret access keys

A "profile name" is just a local nickname. It does **not** exist in the AWS
Console; it only lives on your machine. The console shows your *IAM user name*
(e.g. `administrator`) and *account ID* — different things.

We created a profile named `administrator` pointing at your AWS account
`369506522111`, using an IAM user's access key. The commands were:

```powershell
aws configure set aws_access_key_id AKIA... --profile administrator
aws configure set aws_secret_access_key <secret> --profile administrator
aws configure set region us-east-1 --profile administrator
aws configure set output json --profile administrator
```

`aws configure set` writes one setting at a time straight to the config files
(no interactive prompts, which is why it's reliable).

We verified it worked with:

```powershell
aws sts get-caller-identity --profile administrator
```

`sts get-caller-identity` is the "who am I?" command. It returned the account ID
and the ARN `arn:aws:iam::369506522111:user/administrator`, confirming the
credentials are valid.

### 2.2 Key terms

- **IAM** (Identity and Access Management): AWS's system for users and permissions.
- **IAM user:** a named identity (like `administrator`) that can log in and/or
  hold access keys. Preferred over using the account "root" user for daily work.
- **Access key:** a pair — an **access key ID** (public-ish, starts with `AKIA`)
  and a **secret access key** (shown only once at creation; if lost, make a new one).
- **ARN** (Amazon Resource Name): the unique ID of any AWS thing, e.g.
  `arn:aws:iam::369506522111:user/administrator`.
- **Region:** a geographic location for your resources. We use `us-east-1`
  (N. Virginia). CloudFront HTTPS certificates *must* live here, so it's a sensible default.

### 2.3 Tools used

- **AWS SAM CLI** — builds and deploys the backend (explained in section 4).
- **Python 3.13** — the Lambda language and the test runner's language.
- **Docker** — SAM can use it to build in a Lambda-like container.
- **Git** — version control (not required to run, but part of the challenge).

---

## 3. The frontend (the website files)

Location: the `frontend/` folder.

### 3.1 `index.html` — the resume

Standard HTML. A few things worth understanding:

- The `<head>` has a small inline script that sets a global variable:

  ```html
  <script>
    window.API_URL = "https://ukydqegjbd.execute-api.us-east-1.amazonaws.com/count";
  </script>
  ```

  This is how the page knows where the counter API lives. We left it empty at
  first and filled in the real URL *after* deploying the backend (because the URL
  didn't exist until then). Keeping it as a `window.` variable means the counter
  script doesn't have the URL hardcoded inside it — easy to change in one place.

- At the bottom:

  ```html
  <span id="visitor-count">…</span>
  ...
  <script src="js/counter.js"></script>
  ```

  The `<span>` is an empty placeholder the JavaScript fills in. The `<script>`
  tag is at the end of `<body>` so the HTML is already loaded when the script runs.

- The content (name "Jane Doe", experience, etc.) is placeholder text for you to
  replace with your real resume.

### 3.2 `css/styles.css` — the styling

Plain CSS. Uses **CSS variables** (the `--bg`, `--accent` values in `:root`) so
colors are defined once and reused. Has a `@media (max-width: 520px)` block that
adjusts the layout on small screens (responsive design).

### 3.3 `js/counter.js` — the visitor counter logic

This is the interesting part. Walking through what it does:

```js
(function () {
  "use strict";
  var el = document.getElementById("visitor-count");  // find the placeholder span
  if (!el) return;                                     // bail if it's missing

  var apiUrl = window.API_URL;                         // read the URL set in index.html
  if (!apiUrl) {                                        // if not set, fail gracefully
    el.textContent = "—";
    return;
  }

  fetch(apiUrl, { method: "GET" })                     // call the backend
    .then(function (response) {
      if (!response.ok) throw new Error(...);          // handle HTTP errors
      return response.json();                           // parse the JSON body
    })
    .then(function (data) {
      var count = data.count;                           // read the number
      el.textContent = count.toLocaleString();          // show it (with commas)
    })
    .catch(function (err) {                             // if anything fails
      el.textContent = "—";                             // show a dash, don't crash
    });
})();
```

Key ideas:

- **`fetch()`** is the browser's built-in way to make an HTTP request. It returns
  a **Promise** (a value that arrives later), which is why we chain `.then()`.
- The whole thing is wrapped in `(function () { ... })()` — an **IIFE**
  (Immediately Invoked Function Expression). It runs once and keeps its variables
  out of the global scope.
- **Graceful failure:** if the API is unset or errors, it shows "—" instead of
  breaking the page.

---

## 4. The backend (the counter API)

This is the part defined by AWS SAM. Three AWS services work together.

### 4.1 What is SAM?

**SAM** (Serverless Application Model) is a shorthand for writing CloudFormation.
CloudFormation is AWS's "infrastructure as code" service — you describe resources
in a YAML file and AWS creates them. SAM adds serverless-specific shortcuts so
you write much less YAML for Lambda + API + DynamoDB setups.

The file `template.yaml` is our SAM template. The line
`Transform: AWS::Serverless-2016-10-31` is what tells AWS "this uses SAM
shortcuts, expand them into full CloudFormation."

### 4.2 The three backend services

1. **DynamoDB** — a NoSQL database. We use it to store a single number: the
   visit count. DynamoDB is a good fit because it's cheap, serverless (no server
   to manage), and can do **atomic increments** (see 4.4).

2. **Lambda** — "serverless" compute. You upload a function (our Python code),
   and AWS runs it on demand when called. No server to maintain. You pay only
   per invocation. Our function's job: add 1 to the count and return it.

3. **API Gateway (HTTP API)** — turns your Lambda into a public web URL. When a
   browser does `GET /count`, API Gateway receives it and invokes the Lambda.

### 4.3 Reading `template.yaml` section by section

```yaml
Globals:
  Function:
    Timeout: 10
    MemorySize: 128
    Runtime: python3.13
    Architectures:
      - arm64
```

`Globals` sets defaults for all functions: max 10 seconds per run, 128 MB of
memory, Python 3.13, running on ARM chips (slightly cheaper than x86).

```yaml
VisitorCountTable:
  Type: AWS::DynamoDB::Table
  Properties:
    TableName: !Sub "${AWS::StackName}-visitor-count"
    BillingMode: PAY_PER_REQUEST
    AttributeDefinitions:
      - AttributeName: id
        AttributeType: S
    KeySchema:
      - AttributeName: id
        KeyType: HASH
```

The database table:
- `!Sub "${AWS::StackName}-visitor-count"` builds the name from the stack name.
  `!Sub` means "substitute these variables into the string." `${AWS::StackName}`
  is a built-in value = `cloud-resume-challenge`. So the table is named
  `cloud-resume-challenge-visitor-count`.
- `PAY_PER_REQUEST` = you pay per read/write, no fixed capacity to provision.
  Perfect for tiny, bursty workloads like this.
- The table has one key, `id` (a string, `S`), used as the `HASH` (partition) key.
  Every item must have a unique `id`. We only ever use one item, `id = "visits"`.

```yaml
VisitorCounterFunction:
  Type: AWS::Serverless::Function
  Properties:
    CodeUri: backend/visitor_counter/
    Handler: app.lambda_handler
    Environment:
      Variables:
        TABLE_NAME: !Ref VisitorCountTable
        ITEM_ID: "visits"
    Policies:
      - DynamoDBCrudPolicy:
          TableName: !Ref VisitorCountTable
    Events:
      GetCount:
        Type: HttpApi
        Properties:
          ApiId: !Ref VisitorApi
          Path: /count
          Method: GET
```

The Lambda function:
- `CodeUri` points to the folder with the code.
- `Handler: app.lambda_handler` means "in `app.py`, call the function named
  `lambda_handler`." That's the entry point AWS calls.
- `Environment.Variables` passes config into the code without hardcoding it.
  `TABLE_NAME: !Ref VisitorCountTable` injects the real table name. `!Ref` means
  "give me the value/ID of this resource." The code reads these via
  `os.environ.get(...)`.
- `Policies: DynamoDBCrudPolicy` is a SAM-provided **least-privilege** permission
  bundle. It grants the function permission to read/write **only this one table** —
  not all of DynamoDB. This is the "principle of least privilege": give code only
  the access it needs.
- `Events.GetCount` wires the function to the API: a `GET` on path `/count`
  triggers it.

```yaml
VisitorApi:
  Type: AWS::Serverless::HttpApi
  Properties:
    CorsConfiguration:
      AllowOrigins: ["*"]
      AllowMethods: ["GET"]
      AllowHeaders: ["content-type"]
```

The API Gateway, with **CORS** configured. CORS (Cross-Origin Resource Sharing)
is a browser security rule: by default, a page on domain A cannot call an API on
domain B. Since our page (`cloudfront.net`) and API (`execute-api...amazonaws.com`)
are different domains, the API must explicitly say "I allow cross-origin calls."
`AllowOrigins: ["*"]` means "any domain may call me." (For production you'd
restrict this to your own domain.)

```yaml
Outputs:
  ApiUrl:
    Value: !Sub "https://${VisitorApi}.execute-api.${AWS::Region}.amazonaws.com/count"
  TableName:
    Value: !Ref VisitorCountTable
  FunctionName:
    Value: !Ref VisitorCounterFunction
```

`Outputs` are values the stack reports back after deploying. We used `ApiUrl` to
get the real endpoint and paste it into `index.html`.

### 4.4 The Lambda code — `backend/visitor_counter/app.py`

```python
import json
import os
import boto3

TABLE_NAME = os.environ.get("TABLE_NAME")
ITEM_ID = os.environ.get("ITEM_ID", "visits")
_dynamodb = boto3.resource("dynamodb")

def _table():
    return _dynamodb.Table(TABLE_NAME)

def increment_count():
    response = _table().update_item(
        Key={"id": ITEM_ID},
        UpdateExpression="ADD visits :inc",
        ExpressionAttributeValues={":inc": 1},
        ReturnValues="UPDATED_NEW",
    )
    return int(response["Attributes"]["visits"])

def _response(status, body):
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body),
    }

def lambda_handler(event, context):
    try:
        count = increment_count()
        return _response(200, {"count": count})
    except Exception as exc:
        print(f"Error incrementing visitor count: {exc}")
        return _response(500, {"error": "Could not update visitor count."})
```

Line by line:

- **`boto3`** is the AWS SDK for Python — how the code talks to AWS services.
  `boto3.resource("dynamodb")` gives a high-level DynamoDB client.
- **`increment_count()`** is the heart of it. `update_item` with
  `UpdateExpression="ADD visits :inc"` tells DynamoDB: *on the item with
  `id = "visits"`, add 1 to the `visits` attribute.* This is an **atomic**
  operation — DynamoDB does the read-add-write in one step on its side. That
  matters: if two visitors hit the page at the same moment, you won't lose a
  count (no race condition). If the `visits` attribute doesn't exist yet,
  `ADD` treats it as 0 and creates it. That's why the first call returns 1
  without us having to seed the database.
- `ReturnValues="UPDATED_NEW"` asks DynamoDB to return the value *after* the add,
  so we can report the new count.
- **`lambda_handler(event, context)`** is what AWS calls. `event` holds request
  info; `context` holds runtime info (we don't use either here). It calls
  `increment_count()`, and on success returns HTTP 200 with `{"count": N}`.
- **The response shape** — `statusCode`, `headers`, `body` (a JSON *string*) — is
  the exact format API Gateway expects to turn into a real HTTP response. Note
  `Access-Control-Allow-Origin: "*"` in the headers too (belt-and-suspenders CORS).
- **Error handling:** any exception is caught, logged with `print()` (which goes
  to CloudWatch Logs), and returned as a clean HTTP 500 — the browser gets a
  sensible error instead of a raw stack trace.

### 4.5 `requirements.txt`

Lists Python dependencies. `boto3` is actually already present in the Lambda
runtime, so this is mostly for consistent local test runs.

---

## 5. The tests — `backend/tests/`

Good practice (and part of the challenge): test the Lambda without touching real AWS.

### 5.1 `test_app.py` with `moto`

**`moto`** is a library that *fakes* AWS services in memory. The
`@mock_aws` / `with mock_aws():` wrapper intercepts boto3 calls so they hit a
pretend DynamoDB instead of the real one. This means tests are:
- Free (no AWS charges)
- Fast (no network)
- Safe (can't corrupt real data)

The tests check:
- `test_increment_from_empty` — first increment returns 1.
- `test_increment_is_monotonic` — repeated calls return 1, 2, 3.
- `test_handler_returns_200_and_count` — the handler returns HTTP 200 with the
  right headers and a `count` in the body.
- `test_handler_count_increases_across_calls` — second call is exactly one more
  than the first.
- `test_handler_returns_500_on_error` — if the DB layer throws, the handler
  returns a clean HTTP 500 (uses `monkeypatch` to force an error).

### 5.2 `conftest.py`

A pytest helper. It adds the `visitor_counter/` folder to Python's import path so
the tests can `import app`. Without it, Python wouldn't find the module.

### 5.3 Running them

```powershell
python -m pytest backend/tests -v
```

Result: all 5 passed.

---

## 6. Deploying the backend

### 6.1 Build

```powershell
sam build
```

This reads `template.yaml`, installs the function's dependencies, and copies
everything into a `.aws-sam/build/` folder in the exact layout AWS expects.

### 6.2 Deploy

```powershell
sam deploy --stack-name cloud-resume-challenge --region us-east-1 `
  --profile administrator --capabilities CAPABILITY_IAM --resolve-s3 `
  --no-confirm-changeset --no-fail-on-empty-changeset
```

What the flags mean:
- `--stack-name` — names the CloudFormation stack.
- `--capabilities CAPABILITY_IAM` — you must explicitly acknowledge that the
  stack will create IAM permissions (the Lambda's role). AWS requires this as a
  safety confirmation.
- `--resolve-s3` — SAM needs an S3 bucket to upload your code zip before
  CloudFormation deploys it. This flag auto-creates/uses a managed bucket (that's
  the `aws-sam-cli-managed-default` stack you saw).
- `--no-confirm-changeset` — don't pause for interactive "yes/no" (needed for
  non-interactive runs).
- `--no-fail-on-empty-changeset` — if nothing changed, don't treat it as an error.

CloudFormation then creates the DynamoDB table, the Lambda, its IAM role, and the
API Gateway, in the right order, and reports the outputs.

### 6.3 The result

Outputs returned:
- `ApiUrl`: `https://ukydqegjbd.execute-api.us-east-1.amazonaws.com/count`
- `TableName`: `cloud-resume-challenge-visitor-count`
- `FunctionName`: `cloud-resume-challenge-VisitorCounterFunction-...`

We verified by calling the URL three times — it returned 1, 2, 3. Then we pasted
the URL into `index.html`'s `window.API_URL`.

---

## 7. Hosting the frontend — `frontend-infra.yaml`

This is a second, plain CloudFormation stack (no SAM transform needed) for the
website hosting. Named stack: `cloud-resume-frontend`.

### 7.1 Why this design

The naive approach is "S3 static website hosting," but that only serves HTTP (no
HTTPS) and requires a public bucket. The challenge wants HTTPS. So we use the
recommended modern pattern:

- **Private S3 bucket** — holds the files, blocks all public access.
- **CloudFront** — AWS's CDN (content delivery network). It serves the files over
  HTTPS from locations near the visitor, and it's the *only* thing allowed to read
  the bucket.
- **Origin Access Control (OAC)** — the mechanism that lets CloudFront (and
  nothing else) read the private bucket.

So the bucket is sealed; all traffic goes through CloudFront over HTTPS.

### 7.2 Reading the template

```yaml
SiteBucket:
  Type: AWS::S3::Bucket
  Properties:
    BucketName: !Sub "${AWS::StackName}-site-${AWS::AccountId}"
    PublicAccessBlockConfiguration:
      BlockPublicAcls: true
      BlockPublicPolicy: true
      IgnorePublicAcls: true
      RestrictPublicBuckets: true
    BucketEncryption:
      ServerSideEncryptionConfiguration:
        - ServerSideEncryptionByDefault:
            SSEAlgorithm: AES256
```

- Bucket name includes the account ID because S3 bucket names must be globally
  unique across all of AWS.
- The four `BlockPublic...: true` settings fully lock out public access.
- `BucketEncryption` encrypts files at rest.

```yaml
OriginAccessControl:
  Type: AWS::CloudFront::OriginAccessControl
  Properties:
    OriginAccessControlConfig:
      Name: !Sub "${AWS::StackName}-oac"
      OriginAccessControlOriginType: s3
      SigningBehavior: always
      SigningProtocol: sigv4
```

OAC: CloudFront signs its requests to S3 so S3 can verify they came from this
specific distribution.

```yaml
Distribution:
  Type: AWS::CloudFront::Distribution
  Properties:
    DistributionConfig:
      Enabled: true
      DefaultRootObject: index.html
      PriceClass: PriceClass_100
      Origins:
        - Id: S3Origin
          DomainName: !GetAtt SiteBucket.RegionalDomainName
          OriginAccessControlId: !Ref OriginAccessControl
          S3OriginConfig:
            OriginAccessIdentity: ""
      DefaultCacheBehavior:
        TargetOriginId: S3Origin
        ViewerProtocolPolicy: redirect-to-https
        Compress: true
        CachePolicyId: 658327ea-f89d-4fab-a63d-7e88639e58f6
      CustomErrorResponses:
        - ErrorCode: 403
          ResponseCode: 200
          ResponsePagePath: /index.html
        - ErrorCode: 404
          ResponseCode: 200
          ResponsePagePath: /index.html
```

- `DefaultRootObject: index.html` — visiting the bare URL serves `index.html`.
- `PriceClass_100` — use only the cheapest set of edge locations (NA + Europe).
- `DomainName: !GetAtt SiteBucket.RegionalDomainName` — `!GetAtt` ("get
  attribute") pulls the bucket's internal domain name to use as the origin.
- `ViewerProtocolPolicy: redirect-to-https` — if someone uses http://, bounce
  them to https://. This is what enforces HTTPS.
- `CachePolicyId: 6583...` — an AWS-managed "CachingOptimized" policy (caching
  settings identified by a fixed well-known ID).
- `CustomErrorResponses` — if S3 returns 403/404, serve `index.html` with a 200
  instead. Handy for single-page sites and hides the bucket's existence.

```yaml
BucketPolicy:
  Type: AWS::S3::BucketPolicy
  Properties:
    Bucket: !Ref SiteBucket
    PolicyDocument:
      Statement:
        - Effect: Allow
          Principal:
            Service: cloudfront.amazonaws.com
          Action: s3:GetObject
          Resource: !Sub "${SiteBucket.Arn}/*"
          Condition:
            StringEquals:
              AWS:SourceArn: !Sub "arn:aws:cloudfront::${AWS::AccountId}:distribution/${Distribution}"
```

This permission says: *the CloudFront service may read objects from this bucket,
but only when the request comes from this exact distribution.* That's what makes
the private bucket readable by CloudFront and nothing else.

### 7.3 Deploy and upload

```powershell
# Create the hosting stack
aws cloudformation deploy --template-file frontend-infra.yaml `
  --stack-name cloud-resume-frontend --region us-east-1 --profile administrator

# Upload the files
$bucket = "cloud-resume-frontend-site-369506522111"
aws s3 sync frontend/ "s3://$bucket/" --profile administrator --exclude "index.html" --cache-control "public, max-age=86400"
aws s3 cp frontend/index.html "s3://$bucket/index.html" --profile administrator --content-type "text/html; charset=utf-8" --cache-control "public, max-age=300"
```

- `aws s3 sync` uploads a folder, skipping unchanged files. We excluded
  `index.html` from the sync so we could upload it separately with a *shorter*
  cache time (`max-age=300` = 5 minutes) than the static assets (`max-age=86400`
  = 1 day). That way edits to the HTML show up quickly while CSS/JS stay cached.

Outputs:
- `BucketName`: `cloud-resume-frontend-site-369506522111`
- `DistributionId`: `E1PVM3ISBGPOYT`
- `SiteUrl`: `https://d3hf5icvswiyu1.cloudfront.net`

### 7.4 Updating the site later

After editing files, re-run the sync, then clear CloudFront's cache so visitors
get the new version immediately:

```powershell
aws cloudfront create-invalidation --distribution-id E1PVM3ISBGPOYT --paths "/*" --profile administrator
```

An **invalidation** tells CloudFront to forget its cached copies and fetch fresh
from S3 on the next request.

---

## 8. The one real snag: the SAM permissions error

When we first ran `sam build`, SAM printed long Python tracebacks ending in:

```
PermissionError: [WinError 5] Access is denied:
'C:\Users\SRogouski\AppData\Roaming\AWS SAM\metadata.json'
```

**What it was:** SAM tries to write a small telemetry/metadata file in your
Windows `%APPDATA%\AWS SAM` folder after every command. That folder's permissions
(ACL) were broken, so even reading it failed — and the failure crashed the whole
command at the very end, *after* the actual build/validate had already succeeded.

**Temporary workaround (during the session):** we pointed the `APPDATA`
environment variable at a local writable folder just for SAM, so it wrote its
metadata there instead:

```powershell
$env:APPDATA = "C:\apgit\ResumeChallenge\.sam-home"
```

**Permanent fix (what you did):** in an **Administrator** PowerShell, you took
ownership of the folder and granted your user full control:

```powershell
takeown /F "$env:APPDATA\AWS SAM" /R /D Y
icacls "$env:APPDATA\AWS SAM" /grant "$($env:USERNAME):(OI)(CI)F" /T
```

- `takeown` makes your user the *owner* of the folder (and everything in it, `/R`).
- `icacls ... /grant` gives your user **F** (full control), applied to the folder
  and its contents (`/T`), inheriting to new files (`(OI)(CI)`).

After that, `sam` ran cleanly, so we deleted the `.sam-home` workaround.

Note: "Administrator" here means a *Windows* local admin — totally unrelated to
your AWS `administrator` IAM user. Same word, different systems.

---

## 9. Where everything lives (file map)

```
ResumeChallenge/
├── template.yaml              # SAM: backend (DynamoDB + Lambda + API Gateway)
├── samconfig.toml             # saved SAM deploy settings
├── frontend-infra.yaml        # CloudFormation: S3 + CloudFront hosting
├── README.md                  # quick-start + status
├── .gitignore                 # files git should ignore
├── frontend/
│   ├── index.html             # the resume page (+ window.API_URL)
│   ├── css/styles.css         # styling
│   └── js/counter.js          # visitor-counter fetch logic
├── backend/
│   ├── visitor_counter/
│   │   ├── app.py             # Lambda handler
│   │   └── requirements.txt   # Python deps
│   └── tests/
│       ├── conftest.py        # makes `app` importable in tests
│       └── test_app.py        # 5 pytest tests (moto-mocked)
└── docs/
    └── WALKTHROUGH.md         # this document
```

Deployed AWS stacks:
- `cloud-resume-challenge` — the backend
- `cloud-resume-frontend` — the hosting
- `aws-sam-cli-managed-default` — SAM's helper bucket (auto-created)

---

## 10. Live URLs and resources

- **Website:** https://d3hf5icvswiyu1.cloudfront.net
- **Counter API:** https://ukydqegjbd.execute-api.us-east-1.amazonaws.com/count
- **DynamoDB table:** `cloud-resume-challenge-visitor-count`
- **CloudFront distribution:** `E1PVM3ISBGPOYT`
- **S3 site bucket:** `cloud-resume-frontend-site-369506522111`

---

## 11. What's still left in the challenge

1. **Custom domain** — buy/own a domain, request an HTTPS certificate in AWS
   Certificate Manager (ACM, must be in `us-east-1` for CloudFront), add the
   domain to the CloudFront distribution, and point DNS at it via Route 53.
2. **CI/CD with GitHub Actions** — on every `git push`: run the tests, deploy the
   backend with SAM, sync the frontend to S3, and invalidate CloudFront. This
   removes all the manual deploy steps.
3. **Replace placeholder content** with your real resume in `index.html`.

---

## 12. Glossary (quick reference)

- **CDN** — Content Delivery Network; caches your site near users (CloudFront).
- **CORS** — browser rule controlling cross-domain API calls.
- **CloudFormation** — AWS infrastructure-as-code (YAML → real resources).
- **DynamoDB** — AWS NoSQL database; stores our count.
- **IAM** — AWS identity & permissions.
- **Lambda** — serverless functions; runs our Python on demand.
- **OAC** — Origin Access Control; lets only CloudFront read the private S3 bucket.
- **S3** — AWS object storage; holds the website files.
- **SAM** — Serverless Application Model; shorthand for CloudFormation.
- **Stack** — a group of AWS resources created/managed together by CloudFormation.
- **ARN** — the unique identifier of any AWS resource.
- **Atomic operation** — a database update that happens as one indivisible step,
  avoiding lost updates when things happen at once.
```
