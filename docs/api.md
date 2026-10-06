<div dir="rtl" style="text-align: right; direction: rtl;">

# 🌐 مواصفات واجهات التطبيقات البرمجية (REST & SSE API Specification)
## الدليل التشغيلي لعقود البيانات، مسارات البث اللحظي، وأحداث Server-Sent Events

---

### 1. نظرة عامة على الواجهات (API Overview)

تعتمد المنظومة إطار عمل **FastAPI** فائق السرعة والمبني على معيار **ASGI** غير المتزامن بالكامل (`asyncio`).
تنقسم الواجهات إلى فئتين:
1. **واجهات المحادثة والبث اللحظي (Conversational & SSE Streaming APIs):** عبر مسار البث `/api/chat/stream` المعتمد على أحداث متتالية تمكن واجهات المستخدم من عرض الكلمات والمصادر في الوقت الفعلي.
2. **واجهات إدارة الوثائق والمجموعات (Document & Management REST APIs):** لرفع الملفات، إنشاء المجموعات، ومتابعة تقدم مهام الاستيعاب الخلفية.

---

### 2. بروتوكول أحداث البث اللحظي (SSE Event Protocol)

يتم بث الأحداث بصيغة `text/event-stream` القياسية، وتتضمن الأحداث المتخصصة التالية:

| اسم الحدث (Event Name) | بيانات الحدث (Event Data Payload) | الوصف والتأثير في واجهة المستخدم |
| :--- | :--- | :--- |
| **`event: conversation`** | `{"conversationId": "uuid"}` | يُرسل في مطلع الاتصال لربط جلسة العميل بمعرف المحادثة في قاعدة البيانات. |
| **`event: sources`** | `[{"source_index": 1, "title": "...", "page": 42, ...}]` | يُرسل فور انتهاء البحث لعرض بطاقات المصادر والأدلة المسترجعة فوراً. |
| **`event: chunk`** | `{"text": "الكلمة التالية..."}` | يُرسل مع كل توكن أو مقطع نصي جديد مولد من النموذج اللغوي. |
| **`event: text_done`** | `{"truncated": false, "finishReason": "STOP"}` | إشعار بانتهاء النموذج من توليد النص وبدء مرحلة التدقيق اللاحق. |
| **`event: text_replace`** | `{"text": "النص المعدل بعد إعادة الفهرسة..."}` | يُرسل اختيارياً عند قيام `CitationSanitizer` بحذف أرقام وهمية أو إعادة ترقيم الأقواس. |
| **`event: suggestions`** | `["سؤال مقترح 1", "سؤال مقترح 2"]` | إرسال مقترحات أسئلة تتبعية ذكية مبنية على الجواب المولد. |
| **`event: done`** | `{"conversationId": "...", "model": "...", "groundingAudit": {...}}` | إشعار الختام النهائي وإرسال تقرير كفاية الأدلة وسلامة الاستشهادات. |
| **`event: error`** | `{"error": "رسالة الخطأ التوضيحية"}` | إشعار بحدوث خطأ شبكي أو تجاوز حصص الاستهلاك. |

---

### 3. مواصفات مسار الشات اللحظي (`POST /api/chat/stream`)

#### أ. مخطط الطلب (Request Body Schema - Pydantic v2):
<div dir="ltr" style="text-align: left; direction: ltr;">

```json
{
  "message": "ما هي مقاصد قصة استخلاف آدم في سورة البقرة؟",
  "conversationId": "c8a49df2-5a21-4f76-88d4-5390eb1f13b2",
  "personaMode": "academic_researcher",
  "responseLanguage": "ar",
  "documentIds": ["d1e43b12-0000-4000-a000-000000000001"],
  "collectionId": null,
  "history": [
    { "role": "user", "content": "السلام عليكم" },
    { "role": "assistant", "content": "وعليكم السلام ورحمة الله..." }
  ]
}
```
</div>

#### ب. عينة تدفق أحداث الـ SSE الفعلية (Raw SSE Stream Sample):
<div dir="ltr" style="text-align: left; direction: ltr;">

```http
HTTP/1.1 200 OK
Content-Type: text/event-stream; charset=utf-8
Cache-Control: no-cache, no-transform
Connection: keep-alive
X-Accel-Buffering: no

event: conversation
data: {"conversationId":"c8a49df2-5a21-4f76-88d4-5390eb1f13b2"}

event: sources
data: [{"source_index":1,"document_title":"مجلة تدبر - العدد 21","chapter_title":"مقاصد سورة البقرة","page_number":42,"breadcrumb":"العدد 21 > أبحاث > المبحث الثاني"}]

event: chunk
data: {"text":"تضمنت "}

event: chunk
data: {"text":"قصة استخلاف آدم عليه السلام في سورة البقرة مقاصد تربوية جليلة [1]..."}

event: text_done
data: {"truncated":false,"finishReason":"STOP"}

event: suggestions
data: ["ما الفرق بين خلافة آدم وعمارة الأرض؟","كيف تناولت الدراسات المعاصرة هذا المقصد؟"]

event: done
data: {"conversationId":"c8a49df2-5a21-4f76-88d4-5390eb1f13b2","model":"gemini-3.5-flash-lite","groundingAudit":{"status":"VERIFIED","claimEntailmentScore":94.2}}
```

</div>

---

### 4. مسارات إدارة الوثائق والمجموعات (Document Management APIs)

#### أ. رفع واستيعاب مستند جديد (`POST /api/documents/upload`):
- **النوع:** `multipart/form-data`
- **المعلمات:** `file` (Binary), `title` (string), `author` (string), `collectionId` (UUID optional).
- **الرد (`202 Accepted`):**
  <div dir="ltr" style="text-align: left; direction: ltr;">
  
  ```json
  {
    "documentId": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "jobId": "task_ingest_987654",
    "status": "pending",
    "message": "تم استلام الملف بنجاح وإدراجه في طابور المعالجة والاستيعاب."
  }
  ```
  </div>

#### ب. الاستعلام عن حالة معالجة المستند (`GET /api/documents/{id}/status`):
- **الرد (`200 OK`):**
  <div dir="ltr" style="text-align: left; direction: ltr;">
  
  ```json
  {
    "documentId": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "status": "processing",
    "checkpointStage": "CHUNKING",
    "totalChunks": 0,
    "progressPercent": 60,
    "errorMessage": null
  }
  ```
  </div>

#### ج. البحث المباشر في المقاطع بدون توليد (`POST /api/search`):
- مخصص للباحثين ومحركات الفهرسة السريعة، وينفذ البحث الهجين المباشر ويرجع المقاطع مرتبة ومدمجة بالرتب:
  <div dir="ltr" style="text-align: left; direction: ltr;">
  
  ```json
  {
    "query": "شروط الزكاة",
    "matchCount": 5,
    "results": [
      {
        "chunkId": "f9e8d7c6-b5a4-3210-fedc-ba9876543210",
        "title": "الفقه الميسر",
        "page": 115,
        "combinedScore": 0.048,
        "vectorSimilarity": 0.88,
        "textScore": 0.91,
        "content": "نص المقطع المسترجع..."
      }
    ]
  }
  ```
  </div>

---

### 5. مخططات الأخطاء الموحدة (RFC 7807 Problem Details)

تلتزم المنظومة بمعيار **RFC 7807** في جميع ردود الأخطاء:

<div dir="ltr" style="text-align: left; direction: ltr;">

```json
{
  "type": "https://rag.example.com/errors/rate-limit-exceeded",
  "title": "Rate Limit Exceeded",
  "status": 429,
  "detail": "لقد تجاوزت الحد المسموح به من الطلبات (120 طلب / دقيقة). يرجى الانتظار 30 ثانية.",
  "instance": "/api/chat/stream",
  "correlation_id": "c8a49df2-5a21-4f76-88d4-5390eb1f13b2"
}
```

</div>
