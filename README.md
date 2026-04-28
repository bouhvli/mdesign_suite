# M Design Suite

> Cable route planning and network design platform for Flanders, Belgium.
> Built as a QGIS plugin suite backed by a cloud API using a microservices architecture.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
  - [High-Level Diagram](#high-level-diagram)
  - [Services](#services)
  - [QGIS Plugin Layer](#qgis-plugin-layer)
- [Plugins](#plugins)
- [API Services](#api-services)
  - [auth-service](#auth-service)
  - [org-service](#org-service)
  - [design-service](#design-service)
  - [survey-service](#survey-service)
  - [maps-service](#maps-service)
  - [notify-service](#notify-service)
- [Authentication & Session](#authentication--session)
- [Multi-Tenancy & Organization Config](#multi-tenancy--organization-config)
- [Back-office & Platform Admin](#back-office--platform-admin)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Local Development](#local-development)
  - [Environment Variables](#environment-variables)
- [Adding a New Plugin](#adding-a-new-plugin)
- [API Reference](#api-reference)
- [Contributing](#contributing)
- [Authors](#authors)

---

## Overview

M Design Suite is a professional toolset for fiber optic cable network design and validation in Flanders. It consists of:

- **A QGIS plugin suite** — pure UI layer running on the engineer's machine. Handles dialogs, input forms, layer visualization, and progress feedback.
- **A cloud API platform** — all business logic, geo-processing, validation rules, and data storage run exclusively on the server. Logic never leaves the server.

This separation guarantees that proprietary design rules, validation thresholds, and client-specific configurations are fully protected.

---

## Architecture

### High-Level Diagram

```
User machine (QGIS)                          Trusted Server (Cloud / On-Prem)
┌─────────────────────────┐                 ┌──────────────────────────────────────┐
│  M Design Suite         │                 │  API Gateway                         │
│  (UI layer only)        │──── HTTPS ─────►│  TLS · JWT validation · Rate limits  │
│                         │                 └────────────────────┬─────────────────┘
│  SessionManager         │                                      │
│  (in-memory token,      │                       ┌─────────────┼──────────────┐
│   licensed plugins,     │                       │             │              │
│   org config snapshot)  │              ┌─────────▼──┐  ┌──────▼────┐  ┌─────▼───────┐
└─────────────────────────┘              │auth-service│  │org-service│  │design-svc   │
           ▲                             │            │  │           │  │survey-svc   │
           │                             │ Login      │  │ Orgs      │  │maps-svc     │
           │                             │ Tokens     │  │ Licenses  │  │notify-svc   │
           │                             │ RBAC       │  │ Configs   │  │             │
           │                             │ Users      │  │ Back-off  │  │ Geo-workers │
           │                             └────────────┘  │ Platform  │  │ (Celery)    │
           │                                             └───────────┘  └─────────────┘
           │                                                    │               │
           │                                            ┌───────▼───────────────▼──────┐
           │                                            │  PostgreSQL + PostGIS         │
           │                                            │  (schema per service)         │
           │                                            └──────────────────────────────┘
           │                                                    │
           └────────────────────────────────────────────────────┘
                                                    Back-office & Platform Admin Panel
```

### Services

| Service | Prefix | Responsibility |
|---|---|---|
| `auth-service` | `/api/v1/auth` | Login, JWT issuance, token rotation, user management |
| `org-service` | `/api/v1/backoffice`, `/api/v1/platform` | Organizations, licenses, per-org plugin configs, admin panels |
| `design-service` | `/api/v1/design`, `/api/v1/validation`, `/api/v1/merge`, `/api/v1/images` | All geo-processing: design engine, validation rules, merging, image identification |
| `survey-service` | `/api/v1/survey` | Survey session management, home point collection, demand validation |
| `maps-service` | `/api/v1/maps` | Proxy and cache for Belgian government WFS services |
| `notify-service` | `/api/v1/notifications` | Release notes, notices, per-user notification delivery |

### QGIS Plugin Layer

Each plugin in QGIS contains **only**:
- PyQt5 dialogs and widgets
- Input validation (field-level, client-side)
- HTTP client calling the relevant API service
- Progress feedback and result display

Zero business logic, zero rule constants, zero direct database access.

---

## Plugins

| Plugin | API Service | Description |
|---|---|---|
| `design_tool` | `design-service` | Cable route design: address sync, cluster assignment, trench intersection analysis, report generation |
| `design_validation_tool` | `design-service` | 9-category network validation: crossings, trenches, POC clustering, data quality, feeder rules, and more |
| `external_maps_tool` | `maps-service` | Load and cache Belgian government WFS layers (GRB, GIPOD, Mercator, Omgevingsloket) |
| `survey_app` | `survey-service` | Survey data collection, home point management, demand point validation |
| `image_identify_tool` | `design-service` | Georeferenced image identification and GIS integration |
| `mergin_tool` | `design-service` | Spatial dataset merging and conflict resolution |

---

## API Services

### auth-service

Responsible for all authentication. The **only** service that handles passwords.

```
POST   /api/v1/auth/token          Login → access_token (15 min) + refresh_token (8 hrs)
POST   /api/v1/auth/refresh        Rotate tokens silently (one-time-use refresh)
DELETE /api/v1/auth/logout         Invalidate refresh token on QGIS close

# Internal (not exposed via gateway)
GET    /internal/users/{id}        Called by other services to resolve user details
```

### org-service

Manages all multi-tenancy concerns. Config changes propagate to other services via event bus and cache invalidation.

```
# Back-office (ORG_ADMIN role required)
GET    /api/v1/backoffice/dashboard
GET    /api/v1/backoffice/users
POST   /api/v1/backoffice/users
PATCH  /api/v1/backoffice/users/{id}
DELETE /api/v1/backoffice/users/{id}
GET    /api/v1/backoffice/settings/{plugin}
PATCH  /api/v1/backoffice/settings/{plugin}         # Org-specific rule overrides
DELETE /api/v1/backoffice/settings/{plugin}/reset   # Revert to platform defaults
POST   /api/v1/backoffice/requests                  # Request new plugin license

# Platform admin (PLATFORM_ADMIN role required)
GET    /api/v1/platform/dashboard
GET    /api/v1/platform/orgs
POST   /api/v1/platform/orgs
PATCH  /api/v1/platform/orgs/{id}
GET    /api/v1/platform/licenses
POST   /api/v1/platform/licenses                    # Grant plugin to org
DELETE /api/v1/platform/licenses/{id}               # Revoke
GET    /api/v1/platform/requests                    # Review org requests
PATCH  /api/v1/platform/requests/{id}               # Approve / reject
POST   /api/v1/platform/releases                    # Publish release notice
PATCH  /api/v1/platform/orgs/{id}/settings/{plugin} # Platform-level override

# Internal
GET    /internal/config/{org_id}/{plugin}           # Config resolver — called by design/survey services
```

### design-service

Handles all geo-processing workloads. Heavy operations run on Celery workers with PostGIS.

```
POST   /api/v1/design/run                           # Submit design job → task_id
GET    /api/v1/design/jobs/{task_id}               # Poll status + results
GET    /api/v1/design/sessions/{id}/report          # Download report

POST   /api/v1/validation/run                       # Submit validation job → task_id
GET    /api/v1/validation/jobs/{task_id}
GET    /api/v1/validation/rules                     # Active rule set for caller's org
POST   /api/v1/validation/violations/export

POST   /api/v1/merge/submit
GET    /api/v1/merge/jobs/{task_id}

POST   /api/v1/images/identify
GET    /api/v1/images/{id}
```

### survey-service

```
POST   /api/v1/survey/sessions
GET    /api/v1/survey/sessions/{id}
GET    /api/v1/survey/sessions/{id}/homepoints
POST   /api/v1/survey/sessions/{id}/validate
```

### maps-service

Stateless. Proxies and caches all Belgian government WFS services. No own database.

```
GET    /api/v1/maps/layers                          # Available WFS sources
GET    /api/v1/maps/layers/{source}/features        # Proxied + cached (5 min TTL)
```

Supported sources: `grb_adp`, `gipod`, `mercator_monuments`, `omgevingsloket`, `grb_wgo`

### notify-service

```
GET    /api/v1/notifications                        # Caller's unread notices
PATCH  /api/v1/notifications/{id}/read
```

---

## Authentication & Session

### Token strategy

| Token | Lifetime | Storage |
|---|---|---|
| Access token (JWT) | 15 minutes | In-memory only (`SessionManager` singleton) |
| Refresh token | 8 hours | In-memory on client, bcrypt hash in DB |

Tokens are **never written to disk**. Closing QGIS destroys them. The plugin calls `DELETE /auth/logout` on shutdown to invalidate the refresh token server-side.

### Single Sign-On across plugins

All 6 QGIS plugins share one `SessionManager` singleton:

```python
# mdesign_suite/utils/session_manager.py
session = SessionManager()   # same instance across all plugins

session.login("user@company.be", "password")
# → stores access_token, refresh_token, org_config snapshot, licensed_plugins

# Any plugin, any time:
headers = session.get_headers()           # auto-refreshes if expired
config  = session.get_plugin_config("design_validation_tool")
ok      = session.is_plugin_licensed("mergin_tool")
```

### JWT payload

```json
{
  "sub":              "user-uuid",
  "email":            "user@company.be",
  "org_id":           "org-uuid",
  "org_name":         "Fluvius NV",
  "roles":            ["designer"],
  "licensed_plugins": ["design_tool", "design_validation_tool", "survey_app"],
  "jti":              "unique-token-id",
  "iat":              1711900000,
  "exp":              1711900900
}
```

### Role hierarchy

```
PLATFORM_ADMIN      M.Design team — cross-org, all capabilities
    └── ORG_ADMIN   Company admin — scoped to their organization
            ├── DESIGNER    design_tool + design_validation_tool
            ├── VALIDATOR   design_validation_tool only
            ├── SURVEYOR    survey_app
            └── VIEWER      Read-only across licensed plugins
```

---

## Multi-Tenancy & Organization Config

Every validation rule threshold and design parameter is stored per organization in the database — nothing is hardcoded.

### How it works

1. Each plugin declares a `default_config.py` with platform-wide defaults:

```python
# services/design-service/app/default_configs/validation.py
DEFAULTS = {
    "max_duct_intersections": 8,
    "buffer_radius_meters":   1.0,
    "crossing_angle_threshold_degrees": 15.0,
    "enable_poc_clustering_v2": False,
}
```

2. Org admins override specific values in the back-office:

```
PATCH /api/v1/backoffice/settings/design_validation_tool
{
  "max_duct_intersections": 6,
  "buffer_radius_meters": 1.5
}
```

3. The config resolver merges defaults with overrides at request time (cached in Redis, 5-minute TTL):

```
Final config = DEFAULTS ← org overrides (only non-null fields)
```

4. Rules receive the merged config as a plain dict — pure functions, no DB access:

```python
def validate_duct_crossings(features, config):
    max_ducts = config["max_duct_intersections"]   # 8 for Org A, 6 for Org B
    buffer_m  = config["buffer_radius_meters"]
    # ...
```

---

## Back-office & Platform Admin

### Back-office (per organization)

Accessible by users with `ORG_ADMIN` role. Scoped strictly to their own organization.

| Feature | Description |
|---|---|
| Dashboard | Active jobs, user activity, plugin usage stats |
| User management | Create/update/deactivate users, assign roles |
| Plugin settings | Override default rule values per plugin |
| Requests | Submit license requests or feature requests to M.Design |

### Platform admin (M.Design team only)

Accessible by `PLATFORM_ADMIN` role. Full cross-org visibility.

| Feature | Description |
|---|---|
| Dashboard | Platform-wide metrics, system health, org activity |
| Organization management | Create, configure, suspend organizations |
| License management | Grant or revoke plugin licenses per organization |
| User management | Cross-org user oversight |
| Requests | Review and approve/reject org requests |
| Release management | Publish release notes and breaking-change notices to all orgs |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Web framework | FastAPI + Uvicorn + Gunicorn |
| Database | PostgreSQL 16 + PostGIS 3 (schema-per-service isolation) |
| ORM | SQLAlchemy 2 (async) + Alembic migrations |
| Authentication | `python-jose` (JWT) + `passlib[bcrypt]` |
| Background tasks | Celery 5 + Redis (broker + result backend) |
| Geo processing | Shapely 2 + Fiona + PyProj + GDAL |
| Config cache | Redis (TTL 300s, explicit invalidation on write) |
| WFS proxy cache | `httpx` (async) + Redis + `tenacity` circuit breaker |
| Rate limiting | `slowapi` (per-user, per-org, per-endpoint) |
| API Gateway | Kong OSS or Traefik |
| Service mesh | Linkerd (mTLS between services) |
| Message broker | Redis Streams |
| Distributed tracing | OpenTelemetry → Jaeger |
| Monitoring | Prometheus + Grafana |
| Logging | `structlog` (JSON, request-id + org-id threaded) |
| Container orchestration | Kubernetes (k3s for small deployments) |
| Secrets | Kubernetes Secrets + Vault (production) |
| CI/CD | GitHub Actions (independent pipeline per service) |
| Reverse proxy / TLS | Caddy or Nginx + Let's Encrypt |
| Admin UI | SQLAdmin (FastAPI-native, auto-generated from ORM models) |

---

## Project Structure

```
mdesign_platform/
│
├── services/
│   ├── auth-service/           # Login, tokens, users, RBAC
│   │   ├── app/
│   │   │   ├── main.py
│   │   │   ├── routers/
│   │   │   │   ├── token.py
│   │   │   │   └── users.py
│   │   │   ├── services/
│   │   │   ├── models.py
│   │   │   ├── schemas.py
│   │   │   └── db/
│   │   ├── alembic/
│   │   ├── tests/
│   │   ├── Dockerfile
│   │   └── pyproject.toml
│   │
│   ├── org-service/            # Orgs, licenses, configs, back-office, platform admin
│   │   ├── app/
│   │   │   ├── routers/
│   │   │   │   ├── backoffice/
│   │   │   │   │   ├── users.py
│   │   │   │   │   ├── settings.py
│   │   │   │   │   ├── dashboard.py
│   │   │   │   │   └── requests.py
│   │   │   │   ├── platform/
│   │   │   │   │   ├── orgs.py
│   │   │   │   │   ├── licenses.py
│   │   │   │   │   ├── releases.py
│   │   │   │   │   └── requests.py
│   │   │   │   └── internal/
│   │   │   │       └── config.py   # Called by other services only
│   │   │   ├── services/
│   │   │   ├── models.py
│   │   │   └── db/
│   │   ├── alembic/
│   │   ├── tests/
│   │   ├── Dockerfile
│   │   └── pyproject.toml
│   │
│   ├── design-service/         # Design engine, validation, merge, image identify
│   │   ├── app/
│   │   │   ├── routers/
│   │   │   │   ├── design.py
│   │   │   │   ├── validation.py
│   │   │   │   ├── merge.py
│   │   │   │   └── images.py
│   │   │   ├── services/
│   │   │   ├── rules/          # Pure validation functions (no DB, no FastAPI)
│   │   │   │   ├── crossings.py
│   │   │   │   ├── trenches.py
│   │   │   │   ├── poc_clustering.py
│   │   │   │   └── ...
│   │   │   ├── tasks/          # Celery tasks
│   │   │   └── default_configs/
│   │   ├── alembic/
│   │   ├── tests/
│   │   ├── Dockerfile
│   │   ├── Dockerfile.worker   # Celery worker (separate image)
│   │   └── pyproject.toml
│   │
│   ├── survey-service/         # Survey sessions, home points, demand validation
│   ├── maps-service/           # WFS proxy + Redis cache (stateless)
│   └── notify-service/         # Releases, notices, per-user notifications
│
├── shared/                     # Internal Python package — imported by all services
│   ├── mdesign_shared/
│   │   ├── auth/
│   │   │   ├── jwt_validator.py    # Reads gateway-injected headers
│   │   │   └── principals.py      # UserPrincipal, TokenPayload models
│   │   ├── schemas/
│   │   │   └── common.py          # PaginatedResponse, TaskStatus, ErrorDetail
│   │   ├── middleware/
│   │   │   ├── request_id.py
│   │   │   └── error_handler.py
│   │   └── events/
│   │       └── types.py           # Shared event envelope schemas
│   └── pyproject.toml
│
├── infra/
│   ├── docker-compose.yml      # Full local stack (all services + Redis + PostGIS)
│   ├── k8s/                    # Kubernetes manifests per service
│   ├── kong/                   # API Gateway routing config
│   │   └── kong.yml
│   └── prometheus/
│       └── scrape_config.yml
│
├── .github/
│   └── workflows/
│       ├── auth-service.yml    # Independent CI/CD per service
│       ├── org-service.yml
│       ├── design-service.yml
│       ├── survey-service.yml
│       ├── maps-service.yml
│       └── notify-service.yml
│
└── Makefile
```

---

## Getting Started

### Prerequisites

- Docker + Docker Compose
- Python 3.11+
- QGIS 3.0+ (for the plugin layer)
- `uv` (recommended) or `pip`

### Local Development

```bash
# Clone the repository
git clone https://github.com/bouhvli/mdesign_suite.git
cd mdesign_suite

# Start the full local stack
docker compose -f infra/docker-compose.yml up -d

# Run migrations for each service
make migrate-all

# Verify all services are healthy
make health-check
```

Services will be available at:

| Service | Local URL |
|---|---|
| API Gateway | `http://localhost:8000` |
| auth-service | `http://localhost:8001` |
| org-service | `http://localhost:8002` |
| design-service | `http://localhost:8003` |
| survey-service | `http://localhost:8004` |
| maps-service | `http://localhost:8005` |
| notify-service | `http://localhost:8006` |
| Flower (Celery monitor) | `http://localhost:5555` |
| Jaeger (tracing) | `http://localhost:16686` |
| Grafana (metrics) | `http://localhost:3000` |

### Environment Variables

Copy `.env.example` to `.env` and fill in the values. Never commit `.env`.

```bash
cp .env.example .env
```

Key variables (see `.env.example` for the full list):

```env
# Shared
SECRET_KEY=...                          # JWT signing key — rotate regularly
INTERNAL_API_TOKEN=...                  # Service-to-service auth token
REDIS_URL=redis://localhost:6379/0

# auth-service
AUTH_DB_URL=postgresql+asyncpg://...

# org-service
ORG_DB_URL=postgresql+asyncpg://...

# design-service
DESIGN_DB_URL=postgresql+asyncpg://...
CELERY_BROKER_URL=redis://localhost:6379/1
S3_BUCKET=...
S3_ACCESS_KEY=...
S3_SECRET_KEY=...
```

---

## Adding a New Plugin

Adding a new plugin to the platform requires changes to **at most 2 files** in existing code.

**Step 1** — Decide which service it belongs to (geo-processing → `design-service`, most cases).

**Step 2** — Inside the service, scaffold from the template:

```bash
cp -r services/design-service/app/routers/_template.py \
       services/design-service/app/routers/my_new_plugin.py
```

**Step 3** — Declare default config in `default_configs/my_new_plugin.py`:

```python
DEFAULTS = {
    "threshold_a": 10,
    "radius_meters": 2.0,
}
```

**Step 4** — Register the router in the service's `main.py` (one line):

```python
from app.routers.my_new_plugin import router as my_new_router
app.include_router(my_new_router, prefix="/api/v1/my-new-plugin")
```

**Step 5** — Add the gateway route in `infra/kong/kong.yml` (one line):

```yaml
- paths: ["/api/v1/my-new-plugin"]
  service: design-service
```

**Step 6** — Register the plugin in the `org-service` plugin registry (one migration):

```bash
cd services/org-service
alembic revision --autogenerate -m "register my_new_plugin"
# Add: INSERT INTO plugin_registry (name, display_name) VALUES ('my_new_plugin', 'My New Plugin')
```

**Step 7** — Add the QGIS UI plugin using the shared `SessionManager`:

```python
from mdesign_suite.utils.session_manager import SessionManager

class MyNewApiClient:
    BASE = f"{settings.API_BASE}/api/v1/my-new-plugin"

    def submit_job(self, params: dict) -> str:
        resp = requests.post(
            f"{self.BASE}/run",
            json=params,
            headers=SessionManager().get_headers(),
            timeout=30
        )
        resp.raise_for_status()
        return resp.json()["task_id"]
```

Platform admins can now assign this plugin as a license to organizations via the admin panel.

---

## API Reference

Once running, interactive API documentation is available at:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- OpenAPI JSON: `http://localhost:8000/openapi.json`

Each service also exposes its own docs at its local port (useful during development).

---

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Run the full test suite: `make test-all`
4. Ensure linting passes: `make lint`
5. Open a pull request against `main`

CI runs automatically on every pull request:

```
ruff check     → linting
mypy           → type checking
bandit         → security static analysis
pytest         → unit + integration tests (min 80% coverage)
```

---

## Authors

**Hamza Bouhali & Musa Harouna** — [info@mdesignsolutions.be](mailto:info@mdesignsolutions.be)

Built for fiber optic network design workflows in Flanders, Belgium.

- Repository: [github.com/bouhvli/mdesign_suite](https://github.com/bouhvli/mdesign_suite)
- Issue tracker: [github.com/bouhvli/mdesign_suite/issues](https://github.com/bouhvli/mdesign_suite/issues)
