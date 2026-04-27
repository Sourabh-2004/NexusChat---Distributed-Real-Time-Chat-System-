# NexusChat — Distributed Real-Time Chat System

<div align="center">

**A production-grade, horizontally scalable real-time chat platform** built with FastAPI, WebSockets, Redis Pub/Sub, and PostgreSQL.

[![Python](https://img.shields.io/badge/Python-3.12-blue?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Redis](https://img.shields.io/badge/Redis-7-DC382D?logo=redis&logoColor=white)](https://redis.io)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)](https://postgresql.org)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)](https://docker.com)

</div>

---

## 📋 Table of Contents

- [Architecture](#-architecture)
- [Features](#-features)
- [Quick Start](#-quick-start)
- [Scaling](#-horizontal-scaling)
- [API Documentation](#-api-documentation)
- [Project Structure](#-project-structure)
- [Design Decisions](#-design-decisions)
- [Kubernetes Deployment](#-kubernetes-deployment)


---

## 🏗 Architecture

```
                     ┌──────────────────────────────────┐
                     │         Web Clients (N)          │
                     │    Browser / CLI / Mobile App     │
                     └──────────┬───────────────────────┘
                                │ HTTP / WebSocket
                                ▼
                     ┌──────────────────────────────────┐
                     │     Nginx Load Balancer           │
                     │   (IP hash sticky sessions)       │
                     │   (WebSocket upgrade support)     │
                     └──────────┬───────────────────────┘
                                │
              ┌─────────────────┼─────────────────┐
              ▼                 ▼                 ▼
    ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
    │  FastAPI #1   │  │  FastAPI #2   │  │  FastAPI #3   │
    │  (Stateless)  │  │  (Stateless)  │  │  (Stateless)  │
    │ WS Manager    │  │ WS Manager    │  │ WS Manager    │
    │ Rate Limiter  │  │ Rate Limiter  │  │ Rate Limiter  │
    └──────┬────────┘  └──────┬────────┘  └──────┬────────┘
           │                  │                  │
           └─────────┬────────┴────────┬─────────┘
                     │                 │
              ┌──────▼──────┐   ┌──────▼──────┐
              │    Redis     │   │  PostgreSQL  │
              │  Pub/Sub     │   │  (Persistent │
              │  Cache       │   │   Storage)   │
              │  Presence    │   │              │
              │  Rate Limits │   │              │
              └─────────────┘   └──────────────┘
```

### Message Flow

```
Client A (Instance #1) sends message
    → FastAPI #1 receives via WebSocket
    → Validates JWT + Rate limit check
    → Persists to PostgreSQL (idempotent via idempotency_key)
    → Publishes to Redis Pub/Sub channel "room:{room_id}"
    → Redis fans out to ALL subscribed FastAPI instances
    → FastAPI #1, #2, #3 each deliver to their local WebSocket connections
    → Client B (Instance #2), Client C (Instance #3) receive in real-time
```

---

## ✨ Features

### Core Features
- **Real-time messaging** via WebSockets with ordered delivery
- **Horizontal scaling** — deploy N instances behind Nginx
- **Cross-instance communication** via Redis Pub/Sub
- **JWT authentication** for both HTTP APIs and WebSocket connections
- **Chat rooms** — create, join, leave with role-based membership
- **Message persistence** in PostgreSQL with cursor-based pagination
- **Presence system** — real-time online/offline user tracking

### Advanced Features
- **Typing indicators** with auto-expiry (Redis TTL)
- **Backpressure handling** — slow clients are disconnected to protect the server
- **Heartbeat/ping-pong** — detects and cleans up dead connections
- **Dead letter queue** — failed messages are preserved for debugging
- **Rate limiting** — Redis-backed sliding window (HTTP + WebSocket)
- **Idempotent messages** — client-generated UUIDs prevent duplicates
- **Auto-reconnect** — client reconnects with exponential backoff

### Architecture Features
- **Stateless services** — any instance can handle any request
- **Message broker abstraction** — swap Redis for Kafka without code changes
- **Connection pooling** — SQLAlchemy async pool with pre-ping
- **Graceful shutdown** — clean resource cleanup on termination
- **Health checks** — Nginx + Docker + K8s health monitoring

---

## 🚀 Quick Start

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) (v20+)
- [Docker Compose](https://docs.docker.com/compose/install/) (v2+)

### Start Everything

```bash
# Clone the repository
git clone <repo-url> nexus-chat
cd nexus-chat

# Start all services (single instance)
docker-compose up --build

# Or start with 3 scaled instances
docker-compose up --build --scale app=3
```

### Access the Application

| Service | URL |
|---------|-----|
| **Chat Client** | http://localhost:8080/client/index.html |
| **API Docs (Swagger)** | http://localhost:8080/docs |
| **API Docs (ReDoc)** | http://localhost:8080/redoc |
| **Health Check** | http://localhost:8080/health |

### Quick Test

1. Open http://localhost:8080/client/index.html
2. Click "Create one" to register a new account
3. Create a chat room
4. Open a second browser tab/incognito window
5. Register a different user, join the same room
6. Send messages — they appear in real-time! ⚡

---

## 📈 Horizontal Scaling

### Docker Compose Scaling

```bash
# Scale to 3 instances
docker-compose up --scale app=3

# Scale to 5 instances
docker-compose up --scale app=5

# Scale down
docker-compose up --scale app=1
```

### How It Works

1. **Nginx** distributes requests across all FastAPI instances using IP hash (sticky sessions for WebSocket)
2. **Redis Pub/Sub** ensures messages published on one instance are delivered to clients connected on all other instances
3. **PostgreSQL** provides a single source of truth for persistent data
4. **Each instance is stateless** — no shared in-memory state between instances

### Verify Cross-Instance Communication

```bash
# Check running instances
docker-compose ps

# View logs from all instances
docker-compose logs -f app

# You should see different HOSTNAME values in the logs
# Messages sent from one instance will appear in another's logs
```

---

## 📖 API Documentation

### Authentication

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/auth/register` | Register new user |
| `POST` | `/api/v1/auth/login` | Login, returns JWT tokens |
| `POST` | `/api/v1/auth/refresh` | Refresh access token |
| `GET`  | `/api/v1/auth/me` | Get current user profile |

### Rooms

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST`   | `/api/v1/rooms` | Create new room |
| `GET`    | `/api/v1/rooms` | List rooms |
| `GET`    | `/api/v1/rooms/{id}` | Get room details |
| `POST`   | `/api/v1/rooms/{id}/join` | Join a room |
| `DELETE`  | `/api/v1/rooms/{id}/leave` | Leave a room |
| `GET`    | `/api/v1/rooms/{id}/members` | List room members |

### Messages

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/rooms/{id}/messages` | Paginated chat history |

### WebSocket

| Endpoint | Description |
|----------|-------------|
| `ws://host/ws/chat?token=<jwt>` | Real-time chat connection |

#### WebSocket Events (Client → Server)
```json
{"event": "join_room",    "data": {"room_id": "uuid"}}
{"event": "leave_room",   "data": {"room_id": "uuid"}}
{"event": "message",      "data": {"room_id": "uuid", "content": "Hello!", "idempotency_key": "uuid"}}
{"event": "typing_start", "data": {"room_id": "uuid"}}
{"event": "typing_stop",  "data": {"room_id": "uuid"}}
{"event": "ping",         "data": {}}
```

#### WebSocket Events (Server → Client)
```json
{"event": "message",      "data": {"id": "...", "sender_username": "...", "content": "..."}}
{"event": "presence",     "data": {"user_id": "...", "username": "...", "status": "online"}}
{"event": "typing",       "data": {"user_id": "...", "username": "...", "is_typing": true}}
{"event": "online_users", "data": {"room_id": "...", "users": [...]}}
{"event": "system",       "data": {"content": "User joined the room"}}
{"event": "pong",         "data": {}}
{"event": "error",        "data": {"detail": "...", "code": "..."}}
```

---

## 📁 Project Structure

```
├── app/                          # FastAPI application
│   ├── Dockerfile                # Multi-stage production build
│   ├── requirements.txt          # Python dependencies
│   ├── main.py                   # App entry point + lifespan
│   ├── config.py                 # Pydantic settings
│   ├── api/
│   │   ├── deps.py               # Dependency injection
│   │   ├── routes/
│   │   │   ├── auth.py           # Auth endpoints
│   │   │   ├── rooms.py          # Room CRUD
│   │   │   ├── messages.py       # Message history
│   │   │   └── health.py         # Health check
│   │   └── websocket/
│   │       └── chat.py           # WebSocket handler
│   ├── core/
│   │   ├── security.py           # JWT + password hashing
│   │   ├── rate_limiter.py       # Redis rate limiter
│   │   └── exceptions.py         # Custom exceptions
│   ├── models/                   # SQLAlchemy models
│   ├── schemas/                  # Pydantic schemas
│   ├── services/                 # Business logic layer
│   │   ├── auth_service.py
│   │   ├── room_service.py
│   │   ├── message_service.py
│   │   ├── presence_service.py
│   │   └── typing_service.py
│   ├── messaging/                # Message broker layer
│   │   ├── base.py               # Abstract interface
│   │   ├── redis_broker.py       # Redis Pub/Sub impl
│   │   ├── kafka_broker.py       # Kafka stub
│   │   └── connection_manager.py # WebSocket manager
│   ├── db/                       # Database layer
│   └── alembic/                  # Migration scripts
├── client/                       # Web client (SPA)
│   ├── index.html
│   ├── style.css
│   └── app.js
├── nginx/
│   └── nginx.conf                # Load balancer config
├── k8s/                          # Kubernetes manifests
├── docker-compose.yml
└── README.md
```

---

## 🧠 Design Decisions

| Decision | Choice | Trade-off |
|----------|--------|-----------|
| **Message Broker** | Redis Pub/Sub | ✅ Low latency (~1ms), simple setup. ❌ No message persistence in broker (solved by DB). Abstracted for Kafka swap. |
| **Session Stickiness** | Nginx IP hash | ✅ WebSocket connections stay on same backend. ❌ Potential hotspots. Mitigated by Redis cross-instance delivery. |
| **Idempotency** | Client-generated UUID | ✅ Prevents duplicates on retry. ❌ Extra DB unique constraint. Minimal overhead. |
| **Presence Tracking** | Redis sorted sets + TTL | ✅ Distributed, auto-expiring, efficient queries. ❌ Eventual consistency (~30s). Acceptable for presence. |
| **Rate Limiting** | Redis sliding window | ✅ Accurate, shared across instances. ❌ Extra Redis call per request. Pipelined for efficiency. |
| **Backpressure** | Bounded send queue | ✅ Protects server memory. ❌ Slow clients get disconnected. Better than OOM. |
| **Auth for WS** | JWT in query param | ✅ Works with WebSocket API. ❌ Token in URL (use HTTPS). Standard practice. |
| **DB Migrations** | Alembic (async) | ✅ Version-controlled schema. ❌ Extra setup. Worth it for production. |
| **Dead Letter Queue** | Redis list | ✅ Simple, bounded (10K max). ❌ Not as robust as Kafka DLQ. Sufficient for debugging. |

---

## ☸ Kubernetes Deployment

```bash
# Apply all manifests
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/config.yaml
kubectl apply -f k8s/postgres.yaml
kubectl apply -f k8s/redis.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/ingress.yaml

# Check status
kubectl -n nexus-chat get pods
kubectl -n nexus-chat get svc

# Scale manually
kubectl -n nexus-chat scale deployment chat-app --replicas=5

# HPA is configured to scale between 2-10 replicas based on CPU/memory
```

---



---

## 📄 License

MIT License — feel free to use this as a portfolio project or production starter.
