# CloudVault

CloudVault is an enterprise-grade AWS S3 Storage Management SaaS Platform. It provides a visual, directory-like explorer (behaves similarly to Google Drive or Windows Explorer) to let users connected to their own AWS account manage S3 buckets, structure virtual folder prefixes recursively, upload and catalog files securely, and generate short-lived pre-signed sharing links.

---

## ── Tech Stack ───────────────────────────────────────────────────────────────

*   **Backend Engine**: FastAPI, SQLAlchemy 2.0 (ORM), Alembic (Migrations), Loguru, Uvicorn, Python 3.11.
*   **AWS Integration**: Boto3 (AWS SDK for Python) - STS, S3 operations.
*   **Security & Encryption**: Cryptography (Fernet symmetric encryption for database credentials), JWT stateless authentication, Passlib (bcrypt hash).
*   **Database**: PostgreSQL 15 (Production), SQLite (Testing).
*   **Proxy & Serve**: Nginx (Reverse Proxy & Static Serve), Docker & Docker Compose.

---

## ── Architecture Overview ─────────────────────────────────────────────────────

```
Client (Browser)
       │
       ▼ (Port 80)
┌──────────────┐
│  Nginx Proxy │
└──────┬───────┘
       ├─────────────────────────────────────────┐
       │ (Serve Static Assets)                   │ (Proxy API Requests)
       ▼                                         ▼
┌──────────────┐                          ┌──────────────┐
│  React App   │                          │ FastAPI API  │
└──────────────┘                          └──────┬───────┘
                                                 ├───────────────────────┐
                                                 ▼                       ▼
                                          ┌──────────────┐        ┌──────────────┐
                                          │ S3 Storage   │        │ PostgreSQL DB│
                                          └──────────────┘        └──────────────┘
```

---

## ── Folder Structure ─────────────────────────────────────────────────────────

```
CloudVault/
├── .github/workflows/                 # CI/CD Workflows
│   └── ci.yml                         # Lint & Build Pipeline
├── backend/                           # FastAPI Application
│   ├── api/                           # Route Handlers
│   ├── core/                          # Constants & Database Setup
│   ├── middleware/                    # Cors, Logging Setup
│   ├── models/                        # SQLAlchemy Models
│   ├── repositories/                  # DB query abstractions
│   ├── schemas/                       # Pydantic v2 schemas
│   ├── services/                      # Business & S3 logic
│   ├── utils/                         # Validators & encryption manager
│   └── main.py                        # Entry Point
├── database/
│   └── migrations/                    # Alembic Schema Migrations
├── docker/                            # Production Containers Deployment
│   ├── Dockerfile.backend             # FastAPI Multi-stage build
│   ├── Dockerfile.frontend            # Nginx Static SPA build
│   ├── docker-compose.yml             # Orchestration script
│   └── nginx.conf                     # Reverse proxy config
├── frontend/                          # React Code base
├── requirements.txt                   # Backend library configurations
└── README.md
```

---

## ── Getting Started ─────────────────────────────────────────────────────────

### 1. Locally (Development)

1.  **Clone the Repository**:
    ```bash
    git clone https://github.com/hites/CloudVault.git
    cd CloudVault
    ```

2.  **Set up Backend**:
    ```bash
    cd backend
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    pip install -r requirements.txt
    ```

3.  **Run Migrations**:
    ```bash
    python -m alembic upgrade head
    ```

4.  **Boot Backend**:
    ```bash
    python -m uvicorn backend.main:app --reload
    ```

5.  **Set up Frontend**:
    ```bash
    cd ../frontend
    npm install
    npm run dev
    ```

---

### 2. Using Docker Compose (Production Setup)

Boot up the entire production stack (Nginx proxying Vite React frontend to Python Uvicorn API backed by PostgreSQL database volume) with one command:

1.  **Create `.env`**:
    ```bash
    cp .env.example .env
    # Open .env and populate SECRET_KEY and CREDENTIAL_ENCRYPTION_KEY values
    ```

2.  **Build and Start Containers**:
    ```bash
    cd docker
    docker compose up --build -d
    ```

3.  **Apply migrations inside container**:
    ```bash
    docker compose exec backend alembic upgrade head
    ```

---

## ── API Route Listings ───────────────────────────────────────────────────────

Swagger documentation is available at `http://localhost/docs` when running production Nginx or `http://localhost:8000/docs` in local development.

### Auth Module
*   `POST /api/v1/auth/register` — Create user account
*   `POST /api/v1/auth/login` — Authenticate and receive JWT token
*   `POST /api/v1/auth/logout` — Revoke token state (stateless response)
*   `GET /api/v1/auth/me` — Current user profile

### AWS Connected Accounts
*   `POST /api/v1/aws/connect` — Securely link IAM credentials (decrypted symmetric storage)
*   `POST /api/v1/aws/disconnect` — Disconnect AWS Account from profile
*   `GET /api/v1/aws/status` — Get status verification checks

### S3 Buckets Management
*   `GET /api/v1/buckets` — List S3 buckets (cached/discovered mapping)
*   `POST /api/v1/buckets` — Create globally unique S3 bucket
*   `GET /api/v1/buckets/{bucket_name}` — Get real-time bucket details (versioning, encryption, public access block state)
*   `DELETE /api/v1/buckets/{bucket_name}` — Delete empty bucket
*   `POST /api/v1/buckets/{bucket_name}/exists` — Check global S3 name availability
*   `POST /api/v1/buckets/{bucket_name}/ownership` — Check bucket account ownership

### S3 Folders Prefix Management
*   `POST /api/v1/folders` — Create virtual folder (writes 0-byte folder placeholder on S3)
*   `GET /api/v1/folders` — List folders (supports nesting checks)
*   `GET /api/v1/folders/tree` — Fetch full recursive tree hierarchy
*   `PUT /api/v1/folders/{id}/rename` — Rename folder and S3 objects matching prefix
*   `PUT /api/v1/folders/{id}/move` — Relocate directory folders (validates circular dependencies)
*   `DELETE /api/v1/folders/{id}` — Delete empty virtual folder

### File Operations & Uploads
*   `POST /api/v1/upload/file` — Multipart upload single file to S3
*   `POST /api/v1/upload/files` — Upload multiple files
*   `POST /api/v1/upload/folder` — Upload local folder preserving directories
*   `GET /api/v1/upload/status/{id}` — Poll upload transfer progress
*   `POST /api/v1/upload/retry/{id}` — Heal or retry failed uploads
*   `GET /api/v1/files/{id}/download` — Stream S3 object binary
*   `PUT /api/v1/files/{id}/rename` — Rename file object on S3 and DB metadata
*   `PUT /api/v1/files/{id}/move` — Move file to another virtual folder prefix
*   `POST /api/v1/files/{id}/copy` — Copy file on S3 and generate new metadata
*   `DELETE /api/v1/files/{id}` — Soft delete file (moves to trash, keeps S3 object intact)
*   `POST /api/v1/files/{id}/restore` — Recover file from trash
*   `GET /api/v1/files/types` — Count summaries by extension groups

### Secure Links Sharing
*   `POST /api/v1/share/download` — Generate pre-signed S3 download URL (15m, 1h, 24h, 7d)
*   `POST /api/v1/share/upload` — Generate pre-signed S3 upload POST fields
*   `GET /api/v1/share` — List your active share links
*   `GET /api/v1/share/history` — Audit log of all shared links
*   `DELETE /api/v1/share/{id}` — Revoke sharing link in application database

### Dashboard & Analytics
*   `GET /api/v1/dashboard/overview` — AWS status card summaries
*   `GET /api/v1/dashboard/storage` — Detailed size statistics
*   `GET /api/v1/dashboard/files` — Extensions category maps
*   `GET /api/v1/dashboard/folders` — Hierarchical folder metrics
*   `GET /api/v1/dashboard/recent` — Recent uploads/downloads logs

### Monitoring & Auditing
*   `GET /api/v1/health` — Checks database ping and STS AWS connection
*   `GET /api/v1/metrics` — Connection pool stats and requests counter
*   `GET /api/v1/system/info` — Uptime and runtime versions
*   `GET /api/v1/activity` — Immutable paginated user audit trail logs
*   `GET /api/v1/notifications` — Notification alert lists

---

## ── Security Hardening Practices ───────────────────────────────────────────────

1.  **IAM Security**: CloudVault does not require root credentials. Users should connect restricted IAM user credentials containing policies scoped only to S3/STS actions (`s3:ListBucket`, `s3:PutObject`, etc.).
2.  **Symmetric Encryption**: AWS secret access keys are encrypted before storage in PostgreSQL using AES-256 Fernet symmetric keys. Plair text keys only exist in-memory during requests.
3.  **Pre-Signed URLs**: Download and upload URLs generated during sharing do not modify bucket ACLs. They rely on transient tokens that expire automatically.
4.  **Reverse Proxy Shield**: Nginx filters requests, strips trace headers, and blocks oversized uploads exceeding 100MB to protect backend resource pools.
5.  **Audit Immutable Trail**: Actions are recorded in the `activity_logs` table. This table is designed to be insert-only; update actions are blocked.

---

## ── Future Roadmaps (Version 2.0) ───────────────────────────────────────────────

*   **File Versioning**: Toggle AWS S3 Object Versioning directly from buckets dashboard.
*   **Object Lock & Compliance**: WORM (Write Once, Read Many) S3 locking support for enterprise data compliance.
*   **Virus Scanning**: Trigger bucket-level ClamAV scans on uploads.
*   **Event Notifications**: Connect AWS SNS/SQS alerts to warn users when buckets are modified outside of CloudVault.
*   **Event-driven WebSockets**: Real-time upload percentage notifications using WebSockets instead of polling.
*   **Cost Optimization Analytics**: Report monthly estimated costs based on S3 storage tiers.
*   **Multi-Cloud Storage**: Extend virtual explorer patterns to support Google Cloud Storage (GCS) and Azure Blob storage.

---

## ── License ───────────────────────────────────────────────────────────────────

Distributed under the MIT License. See [LICENSE](LICENSE) for details.
