# Credit Card Smart Advisor & Ingestion Backend

An enterprise-grade, high-performance asynchronous backend powering credit card recommendations, reward calculations, and catalog ingestion from SaveSage Club APIs. Built for seamless pairing with a Flutter mobile frontend, deployable on **100% free-tier cloud resources** (Neon PostgreSQL, Upstash Redis, and Oracle Cloud Always Free VM).

---

## 🌟 Key Features

1. **"Which Card Should I Use?" Advisor Engine**:
   - Takes a spend category (e.g. *Dining*, *Grocery*, *Fuel*, *Rent*) and spend amount (₹).
   - Scans the user's active wallet cards, evaluates category-specific accelerated multipliers, base reward rates, exclusions, and forex markups.
   - Recommends the #1 optimal card with projected reward points, monetary return in INR, and ranked alternatives.
2. **Offline Reward Calculator**:
   - Re-implemented offline calculation engine matching SaveSage's mathematical reward valuation.
   - Computes reward points, cash equivalents, and projected annual savings against the top-performing benchmark card on the market.
3. **Decoupled Asynchronous Ingestion & Cron Scheduler**:
   - Ingests 700+ cards, 40 banks, 16 categories, and 5 discrete perk tabs (`earn-categories`, `benefits-and-offers`, `lounge-access`, `milestones`, `redemption-options`).
   - Powered by `APScheduler` (running weekly cron sync) and manual trigger endpoints with **Upstash Redis distributed locking**.
   - Zero direct frontend calls to third-party APIs.
4. **App Store & PCI-DSS Compliant Zero-Knowledge Design**:
   - Sensitive 16-digit card numbers and CVVs are stored **strictly on the user's local mobile device** (Hardware Secure Enclave / Biometrics).
   - The backend stores zero sensitive cardholder data, eliminating PCI-DSS compliance scope and ensuring 100% compliance with Google Play Store & Apple App Store financial data safety policies.
5. **High-Speed Caching**:
   - Upstash Redis cache-aside caching (1-hour to 24-hour TTLs) with resilient in-memory fallback.

---

## 🏛️ System Architecture

```
[Flutter Mobile App]
       │
       ▼ (HTTPS / JSON Envelope)
[Nginx Reverse Proxy & Rate Limiter] (Port 80/443)
       │
       ▼
[FastAPI Asynchronous Core] (Port 8000)
   ├── Neon Serverless PostgreSQL (AsyncPG, Pooled Connection)
   ├── Upstash Serverless Redis (Cache & Distributed Lock)
   └── APScheduler Cron Worker ──▶ SaveSage Club APIs (Ingestion)
```

---

## 🚀 Quick Start (Local Development)

### 1. Prerequisites
- Python 3.12+ (or Python 3.14)
- Git

### 2. Clone and Setup Environment
```bash
# Clone the repository
git clone <repo-url>
cd credit-card-datas

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
*(By default, `.env` uses a local SQLite database and in-memory cache fallback so you can run the service immediately without external credentials).*

### 4. Run Migrations & Seed Demo Data
```bash
# Apply database migrations
alembic upgrade head

# Seed sample banks, categories, and top popular cards
python scripts/seed_demo_data.py
```

### 5. Start the FastAPI Development Server
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
Open **[http://localhost:8000/docs](http://localhost:8000/docs)** to view the interactive Swagger API documentation.

---

## 🧪 Running the Test Suite

The test suite covers health probes, JWT authentication, card catalog queries, the smart advisor recommendation engine, and the reward calculator:

```bash
pytest -v
```

---

## 🔄 Running Data Ingestion (SaveSage Sync)

### Option A: From Terminal (CLI Script)
```bash
# Test ingestion with 5 cards and tabs
python scripts/run_sync.py --limit 5

# Full ingestion of all ~734 cards and tabs
python scripts/run_sync.py
```

### Option B: Via Authenticated Admin API
```bash
curl -X POST "http://localhost:8000/api/v1/admin/sync/trigger" \
  -H "X-Admin-API-Key: admin-secret-sync-key" \
  -H "Content-Type: application/json" \
  -d '{"sync_tabs": true, "limit_cards": 10}'
```

Check sync status:
```bash
curl "http://localhost:8000/api/v1/admin/sync/status" \
  -H "X-Admin-API-Key: admin-secret-sync-key"
```

---

## 🌐 Deploying to Oracle Cloud Free Tier VM

Both the FastAPI service and Nginx reverse proxy fit comfortably inside the Oracle Cloud Always Free VM (Ubuntu 22.04 LTS).

### 1. Provision VM & Install Docker
```bash
sudo apt update && sudo apt install -y docker.io docker-compose git
sudo usermod -aG docker $USER
```

### 2. Configure Cloud Database & Redis (.env)
Update `.env` on your Oracle VM with your free-tier credentials:
```ini
ENVIRONMENT=production
DEBUG=false
HOST=0.0.0.0
PORT=8000

# Neon Serverless PostgreSQL Connection String (with asyncpg driver):
DATABASE_URL=postgresql+asyncpg://neondb_owner:YOUR_PASSWORD@ep-xyz-pooler.ap-southeast-1.aws.neon.tech/neondb?ssl=require

# Upstash Redis URL:
REDIS_URL=rediss://default:YOUR_PASSWORD@xyz.upstash.io:6379
REDIS_ENABLED=true

# Security
JWT_SECRET_KEY=generate-a-secure-random-32-char-key
ADMIN_API_KEY=your-secure-admin-api-key
```

### 3. Launch with Docker Compose
```bash
docker-compose up -d --build
```

### 4. Enable Free SSL via Certbot (Optional)
```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d api.yourdomain.com
```

---

## 📡 API Reference Catalog

All endpoints return a unified JSON response envelope:
```json
{
  "success": true,
  "message": "Operation completed successfully",
  "data": { ... },
  "meta": null,
  "error": null
}
```

| Method | Endpoint | Description | Auth Required |
|---|---|---|:---:|
| `GET` | `/api/v1/health` | Deep health probe (Neon DB & Upstash Redis) | No |
| `POST` | `/api/v1/auth/register` | Register new user account | No |
| `POST` | `/api/v1/auth/login` | Obtain Bearer JWT token | No |
| `GET` | `/api/v1/auth/me` | Retrieve authenticated user profile | Bearer JWT |
| `GET` | `/api/v1/cards` | Paginated cards with multifaceted filters | No |
| `GET` | `/api/v1/cards/{slug}` | Single card detail with available tabs | No |
| `GET` | `/api/v1/cards/{slug}/tabs/{tab}` | Deep perk tab (`earn-categories`, `lounge-access`, etc.) | No |
| `GET` | `/api/v1/banks` | List all 40 indexed banks | No |
| `GET` | `/api/v1/categories` | List all 16 spend categories | No |
| `GET` | `/api/v1/user-cards` | List cards in the authenticated user's wallet | Bearer JWT |
| `POST` | `/api/v1/user-cards` | Add a card from catalog to personal wallet | Bearer JWT |
| `PATCH` | `/api/v1/user-cards/{id}` | Update wallet card (nickname, last 4 digits) | Bearer JWT |
| `DELETE` | `/api/v1/user-cards/{id}` | Remove card from user's wallet | Bearer JWT |
| `POST` | `/api/v1/advisor/recommend` | **Smart Advisor**: "Which card to use?" | Optional JWT |
| `POST` | `/api/v1/calculator/calculate` | Offline Reward Calculator | No |
| `POST` | `/api/v1/admin/sync/trigger` | Trigger manual data synchronization | Admin Key / JWT |
| `GET` | `/api/v1/admin/sync/status` | View sync status & database record counts | Admin Key / JWT |
| `GET` | `/api/v1/admin/sync/history` | View sync audit logs | Admin Key / JWT |

---

## 🛡️ Security & Privacy Notice (For App Store Reviewers)

This application adheres to the principle of least privilege and strict data minimization:
- **Zero PAN Transmission**: Full 16-digit Primary Account Numbers (PAN) and CVVs are neither requested by, transmitted to, nor stored on this backend server.
- **On-Device Biometric Vault**: If the user chooses to store their card number for one-tap clipboard copy, that data is encrypted using the device's hardware Secure Enclave (Apple Keychain on iOS / Android Keystore) and protected by biometric authentication (FaceID/TouchID/Fingerprint).
- **Out of PCI-DSS Scope**: The backend architecture remains completely isolated from cardholder data environment (CDE) scope.

---

## 📄 License
MIT License. Built with clean code principles for enterprise scalability.
# CreditVance-Backend
