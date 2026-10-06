<div dir="rtl" style="text-align: right; direction: rtl;">

# 📈 الملاحظية والمراقبة والقياس (Observability & Telemetry Framework)
## الدليل المعماري للتتبع الموزع، السجلات المهيكلة، ومقاييس الأداء التراكمية

---

### 1. فلسفة الملاحظية في بيئات الإنتاج (Observability Philosophy)

الأنظمة الإنتاجية لا يمكن إدارتها بناءً على جمل الطباعة العشوائية (`print` statements).
تعتمد هذه المنظومة على **المثلث الذهبي للملاحظية (The 3 Pillars of Observability)**:
1. **السجلات المهيكلة (Structured JSON Logs):** بصيغة قابلة للفهرسة المباشرة في منصات مثل Elasticsearch, Loki, أو CloudWatch مع معرف تتبع موحد (`Correlation ID`).
2. **المقاييس اللحظية (Prometheus Metrics):** لقياس أزمنة الاستجابة، معدلات الإصابة في الكاش، استهلاك التوكنز، والرموز اللغوية المتبادلة.
3. **التتبع الموزع (Distributed Tracing):** تتبع رحلة الطلب خطوة بخطوة عبر مسارات الكاش، التضمين، قاعدة البيانات، ونموذج التوليد.

---

### 2. تدفق معرف الارتباط الموحد (`Correlation ID Flow`)

</div>

<div dir="ltr" style="text-align: left; direction: ltr;">

```mermaid
sequenceDiagram
    autonumber
    Client as Browser / External Client
    participant MW as Correlation Middleware
    participant Core as RAG Orchestrator
    participant PG as PostgreSQL
    participant Redis as Redis Cache
    participant LLM as Gemini / OpenAI

    Client->>MW: Request [X-Correlation-ID: req_abc123] (or Auto-Generated)
    Note over MW: Bind correlation_id to AsyncContextVar
    MW->>Core: Pass Context with Trace ID
    Core->>Redis: Check L1 Cache [Logged with req_abc123]
    Core->>PG: Hybrid SQL Search [Comment: /* trace: req_abc123 */]
    Core->>LLM: Stream Inference [Telemetry tag: req_abc123]
    Core-->>MW: Completed Stream
    MW-->>Client: Response Headers [X-Correlation-ID: req_abc123]
```

</div>

<div dir="rtl" style="text-align: right; direction: rtl;">

---

### 3. السجلات المهيكلة بصيغة JSON (`Structured JSON Logging`)

تُبنى السجلات باستخدام مكتبة `structlog` في بايثون، مما ينتج سطور JSON قياسية خالية من البيانات الحساسة أو المفاتيح الصريحة:

<div dir="ltr" style="text-align: left; direction: ltr;">

```json
{
  "timestamp": "2026-10-06T14:22:30.145Z",
  "level": "info",
  "event": "retrieval_completed",
  "correlation_id": "c8a49df2-5a21-4f76-88d4-5390eb1f13b2",
  "user_identifier": "usr_99182",
  "language": "ar",
  "duration_ms": 14.8,
  "candidates_count": 18,
  "top_similarity": 0.892,
  "hybrid_weights": { "vector": 0.7, "keyword": 0.3 }
}
```

</div>

---

### 4. مقاييس بروميثيوس الأساسية (`Prometheus Metrics Registry`)

تُعرض المقاييس عبر نقطة النهاية القياسية: `/metrics` للمراقبة التلقائية في Prometheus و Grafana:

| اسم المقياس (Metric Name) | النوع (Type) | التسميات (Labels) | الوصف الهندسي |
| :--- | :--- | :--- | :--- |
| `rag_requests_total` | Counter | `endpoint, status, persona` | إجمالي عدد طلبات الاستعلام المعالجة. |
| `rag_cache_hits_total` | Counter | `tier (l1_redis, l2_vector)` | عدد مرات نجاح الاسترجاع من الكاش. |
| `rag_cache_misses_total` | Counter | `reason (unmatched, not_equivalent)` | عدد مرات الإخفاق في الكاش والانتقال لـ RAG. |
| `rag_retrieval_duration_seconds` | Histogram | `method (hybrid, dense, lexical)` | توزيع أزمنة استعلام قاعدة البيانات. |
| `rag_time_to_first_token_seconds`| Histogram | `model, stream_type` | زمن وصول أول توكن للمستخدم (TTFT). |
| `rag_tokens_consumed_total` | Counter | `model, type (prompt, completion)` | إجمالي التوكنز المستهلكة في النماذج. |
| `rag_evidence_abstentions_total` | Counter | `language, reason` | عدد مرات امتناع النظام عن الإجابة لضعف الأدلة. |
| `rag_active_sse_connections` | Gauge | `endpoint` | عدد جلسات البث اللحظي النشطة حالياً. |

---

### 5. نقاط فحص الصحة والجاهزية (`Health & Readiness Probes`)

تتضمن المنظومة نقطتي فحص متوافقتين مع Kubernetes و Docker Healthcheck:

1. **فحص الحيوية (`GET /api/health/liveness`):**
   - يتأكد من أن خادم FastAPI يعمل ويستقبل اتصالات HTTP (يرد بـ `200 OK` فوري).
2. **فحص الجاهزية (`GET /api/health/readiness`):**
   - يفحص الاتصال الحقيقي بقاعدة بيانات PostgreSQL (تنفيذ `SELECT 1`).
   - يفحص الاتصال الحقيقي بـ Redis (تنفيذ `PING`).
   - يتأكد من توفر مفتاح الاعتماد لخدمة التضمين.
   - في حال تعطل أي مكون، يُرجع `503 Service Unavailable` مع تقرير تفصيلي بحالة كل خدمة:
   <div dir="ltr" style="text-align: left; direction: ltr;">
   
   ```json
   {
     "status": "ready",
     "timestamp": "2026-10-06T14:25:00Z",
     "checks": {
       "database": "connected (latency: 1.2ms)",
       "redis": "connected (latency: 0.5ms)",
       "embedding_service": "configured",
       "worker_queue": "active"
     }
   }
   ```
   </div>

---

### 6. تتبع التكلفة والرموز اللغوية (Token & Cost Telemetry)

- يتم تتبع التوكنز في كل استجابة: `prompt_tokens` و `completion_tokens` وحساب التكلفة التقديرية بالدولار بناءً على أسعار المزود (Google Gemini أو OpenAI).
- تُسجل هذه البيانات في حقل `token_usage` بجدول `chat_messages`، مما يسمح لإداريي النظام باستخراج تقارير تكلفة شهرية لكل مستخدم أو لكل مجموعة معرفية.

</div>
