# Production RAG Blueprint — Project Map

## [TECH_STACK]
- **Language & Runtime**: Python 3.12+ (tested on Python 3.14)
- **API Framework**: FastAPI, Pydantic v2, Uvicorn (ASGI)
- **Persistence & Vector DB**: PostgreSQL 16+, pgvector (HNSW cosine index)
- **Database ORM & Migrations**: SQLAlchemy 2.0 (async), Alembic
- **Caching & Locks**: Redis 7.4+ (asyncio, pipeline rate limiting, single-flight mutex)
- **Background Workers**: Taskiq + Redis (Async background ingestion pipeline)
- **AI/LLM Client**: Multi-provider Protocol (Gemini 3.5, OpenAI, Anthropic, Ollama - gemini-2.5 excluded)
- **Observability**: Structured JSON logging, OpenTelemetry tracing, Prometheus metrics
- **Deployment**: Multi-stage Docker, Docker Compose, Nginx reverse proxy

## [SYSTEM_FLOW]
```
User Query -> PolicyGuard (Deterministic <1ms) -> L1 Exact Cache (Redis <5ms)
           -> Query Normalization & Language Router (ar/en/es/pt)
           -> IntentRouter (new/follow_up/transform/clarify in parallel with DB)
           -> EmbeddingService (Batch/Fallback) -> L2 Vector Semantic Cache (pgvector + EquivalenceVerifier)
           -> Hybrid RRF Search (pgvector HNSW + Lexical GIN) -> ContextExpander (Parent-Child)
           -> Deterministic/Neural Reranker -> DiversityGuard -> EvidenceEvaluator (Sufficiency Check)
           -> ShapeDetector & AdaptiveContextManager -> LLM Stream -> CitationSanitizer & Validator
           -> SSE Response + L1/L2 Cache Write + Memory Extraction
```

## [ARCHITECTURE]
```
src/
├── api/             # FastAPI routes, SSE streaming, middleware, auth, rate limiting
├── core/            # Config, security, key vault, logging, exceptions
├── domain/          # Protocols, interfaces, data models, entities
├── ingestion/       # Extensible parsers (PDF, DOCX, MD, TXT), structural & semantic chunkers
├── retrieval/       # Dense, sparse, hybrid 5-way RRF, language routing, query transform
├── reranking/       # Deterministic fast reranker + optional cross-encoder
├── caching/         # L1 Redis + L2 pgvector + single-flight mutex + equivalence verifier
├── context/         # Token budgeting, whole-turn compression, untrusted evidence boundary
├── llm/             # Model provider abstraction (Gemini 3.5, OpenAI, Anthropic, Ollama)
├── citations/       # Bracket parser, phantom stripping, sequential alignment, entailment
├── evaluation/      # Recall@K, Precision@K, MRR, groundedness, hallucination detection
├── observability/   # Metrics collector, correlation IDs, audit logs, health checks
└── workers/         # Taskiq worker pipeline (Validate -> Parse -> Chunk -> Embed -> Index)
```

## [VERIFIABLE_MILESTONES]
- [x] **M0**: Comprehensive Architectural Documentation Package (`docs/`) & ADRs (Bilingual RTL)
- [x] **M1**: Core Infrastructure, Domain Contracts & Database Schemas (Alembic + pgvector)
- [x] **M2**: Ingestion Pipeline & Parsers (PDF, DOCX, MD, TXT) with Parent-Child Chunking
- [x] **M3**: Retrieval Engine (5-Way Hybrid RRF, LanguageRouter, Query Transformer)
- [x] **M4**: Semantic Caching Engine (L1 Redis, L2 pgvector, Single-Flight, Equivalence Verifier)
- [x] **M5**: Context Engineering, PolicyGuard & Intent Routing
- [x] **M6**: Multi-Provider LLM Streaming, Citation Sanitizer & Evidence Evaluator
- [x] **M7**: FastAPI REST & SSE API Layer, Auth Middleware & Redis Rate Limiting
- [x] **M8**: Background Ingestion Worker Pipeline (Taskiq) & Job Checkpoints
- [x] **M9**: Evaluation Framework & Observability Subsystem
- [x] **M10**: Comprehensive Test Suite (Unit, Integration, E2E, Failure Scenarios)
- [x] **M11**: Dockerization, Docker Compose, CI/CD & Final Production Verification

## [ORPHANS & PENDING]
- None (All 12 Milestones M0 through M11 successfully executed, tested, and verified)



