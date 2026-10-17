# Project Brief: Warehouse Inventory & Storage Management REST API (WMS Core)

## 1. Executive Summary

The goal of this project is to build a robust, scalable, and secure backend RESTful API that serves as the core engine for warehouse storage, container tracking, and stock inventory management. The system will manage the physical layout of warehouse locations hierarchically, control nested physical containers (pallets, boxes, totes), record granular stock allocations with batch and expiry tracking, and ensure 100% auditability through movement logs and transactional integrity.

---

## 2. Business Objectives & Success Criteria

* **Full Inventory Traceability:** Ensure complete end-to-end auditability of every single stock creation, displacement, split, merge, and write-off.
* **Operational Accuracy:** Prevent negative inventory, over-capacity placements, orphaned containers, and concurrency race conditions.
* **Developer Experience & Seamless Integration:** Provide standardized REST conventions, OpenAPI documentation, and machine-readable, actionable error handling following RFC 7807 (`problem+json`).
* **High Reliability:** Achieve sub-second query performance and guarantee data consistency via atomic multi-resource transactions.

---

## 3. Project Scope

### In Scope

1. **Hierarchical Warehouse Locations (REQ-001 – REQ-005):**
* Multi-tier location tree (`warehouse` > `zone` > `aisle` > `rack` > `shelf` > `bin`).
* Location lifecycle management: CRUD operations with soft delete.
* Capacity and status enforcement (prevent reducing capacity below current occupancy or deleting occupied locations).
* Location relocation logic (moving branches without circular nesting).


2. **Container Management (REQ-006 – REQ-010):**
* Unique container tracking (SSCC / barcode identifiers).
* Support for container nesting and physical movement across locations or parent containers.
* Maximum weight and dimension constraints with automatic validation.
* Safe deletion (prevent deleting containers holding stock/nested containers) and movement history tracking.


3. **Stock & Inventory Operations (REQ-011 – REQ-019):**
* SKU registration referencing quantities, UoM, lot/batch, and expiry dates (either in locations or within containers).
* Status handling (`available`, `blocked`, `quarantine`).
* Complex stock operations:
  * Full and partial stock movements.
  * Record splitting and merging (summing matching SKU/lot/status).
  * Grouping stock into new containers (palletization/packing) and ungrouping (releasing stock directly into the parent location).
  * Mandatory adjustment and write-off reason codes.


4. **Audit Trail & Traceability (REQ-020):**
* Immutable movement log capturing entity, operation type, user, timestamp, before/after states, and operational reason.


5. **Security, Architecture & Cross-Cutting Non-Functional Requirements (REQ-021 – REQ-038):**
* **Transactional Integrity:** ACID guarantees and rollback for multi-record operations (REQ-021).
* **Concurrency Control:** Optimistic locking via ETag/version headers (REQ-022).
* **Auth & RBAC:** JWT/OAuth2 token enforcement with `admin`, `supervisor`, and `operator` role boundaries (REQ-023).
* **Standardized Error Architecture:** Strict adherence to RFC 7807 (`application/problem+json`), machine-readable error codes (e.g., `LOCATION_NOT_EMPTY`, `STOCK_INSUFFICIENT_QUANTITY`), field-level validation lists, localization (EN, ES, CA), and leak-proof 5xx responses with distributed `trace_id` linkage (REQ-024, REQ-029 – REQ-038).
* **Performance & Quality:** p95 latency < 300 ms for single-item reads and < 1 s for list/aggregate queries over 100k records; automated CI pipeline with $\ge 80\%$ test coverage (REQ-026, REQ-027).
* **Observability & Deployment:** Dockerized service, health check endpoints, structured JSON logging, and OpenAPI 3 / Swagger UI specifications (REQ-025, REQ-028).



### Out of Scope

* Product Master Data management (SKUs are accepted as external validated string references).
* Hardware driver integration (direct physical printer or scanner device drivers).
* Purchase order receiving / sales order shipping orchestration (covered in future ERP integration phases).

---

## 4. Key Functional Modules & Technical Specifications

| Module | Requirements | Key HTTP Endpoints | Main Business Rules & Constraints |
| --- | --- | --- | --- |
| **Location Engine** | REQ-001 – REQ-005 | `POST /locations`<br>

<br>`GET /locations`<br>

<br>`PATCH /locations/{id}`<br>

<br>`DELETE /locations/{id}`<br>

<br>`POST /locations/{id}/move` | Code uniqueness per warehouse; non-cyclic hierarchy; soft delete only when childless and empty; capacity guardrails. |
| **Container Engine** | REQ-006 – REQ-010 | `POST /containers`<br>

<br>`GET /containers`<br>

<br>`PATCH /containers/{id}`<br>

<br>`DELETE /containers/{id}`<br>

<br>`POST /containers/{id}/move`<br>

<br>`POST /containers/{id}/ungroup` | Unique SSCC/barcode; nested container support without cycles; max weight verification; automatic stock displacement upon move. |
| **Inventory Core** | REQ-011 – REQ-019 | `POST /stocks`<br>

<br>`GET /stocks`<br>

<br>`PATCH /stocks/{id}`<br>

<br>`DELETE /stocks/{id}`<br>

<br>`POST /stocks/{id}/move`<br>

<br>`POST /stocks/merge`<br>

<br>`POST /stocks/{id}/split`<br>

<br>`POST /stocks/group` | Positive quantities; atomic split/merge/group; mandatory reason codes for adjustments and write-offs. |
| **Audit & Logs** | REQ-020 | `GET /movements` | Immutable audit trail with entity type, user, timestamp, before/after states, and reason filtering. |

---

## 5. Non-Functional & Governance Standards

* **API Design Standard:** RESTful JSON following strict HTTP semantics (400, 401, 403, 404, 409, 412, 422, 429, 500, 503).
* **Data Protection & Compliance:** Strict error masking (no stack traces, database schema details, or library versions exposed externally).
* **Target Environment:** Containerized application (Docker) deployable to Kubernetes/cloud environments with structured health checks and distributed tracing (`X-Request-ID`).

---

## 6. Project Deliverables & Milestones

1. **Milestone 1: Architectural Foundation & CI/CD Setup**
* Database schema design with transaction support and optimistic locking.
* Authentication & RBAC middleware integration.
* RFC 7807 error handler and OpenAPI skeleton.


2. **Milestone 2: Location & Container Hierarchy Engine**
* Location and container CRUD, nested moves, and capacity validation.


3. **Milestone 3: Stock Management & Advanced Movements**
* Stock allocations, split/merge/grouping atomic transactions, and movement history logging.


4. **Milestone 4: Performance, Localization & Production Readiness**
* Stress testing with 100k records, multi-language message bundles (EN/ES/CA), Docker image delivery, and $\ge 80\%$ test suite validation.