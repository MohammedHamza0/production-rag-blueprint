<div dir="rtl" style="text-align: right; direction: rtl;">

# 🔄 مسار معالجة الاستعلام الكامل (End-to-End Query Lifecycle Pipeline)
## الدليل التشغيلي لمسار التدفق اللحظي للـ RAG من الاستلام حتى إنهاء البث

---

### 1. نظرة عامة على دورة حياة الطلب (Pipeline Overview)

يمثل مسار معالجة الاستعلام في هذه المنظومة تسلسلاً هندسياً دقيقاً ومحكماً، صُمم خصيصاً للقضاء على نقاط الاختناق الشائعة في أنظمة الـ RAG، مثل:
1. **تأخير أول توكن (High Time-to-First-Token - TTFT)** الناجم عن استدعاءات LLM المتتالية قبل التوليد.
2. **استنزاف موارد الخادم والتكلفة المالية** بسبب معالجة التحيات والأسئلة الخارجة عن النطاق.
3. **التدافع المتزامن (Cache Stampede / Thundering Herd)** عند ورود نفس السؤال من مئات المستخدمين في الوقت ذاته.
4. **تلوث اللغات والهلوسة المرجعية** عند اختلاف لغة السؤال أو ضعف السند المعرفي في الوثائق.

---

### 2. مخطط تدفق الحالة اللحظية (Detailed State Flow Diagram)

</div>

<div dir="ltr" style="text-align: left; direction: ltr;">

```mermaid
sequenceDiagram
    autonumber
    actor Client as User / Browser
    participant API as FastAPI Router
    participant PG as PolicyGuard (<1ms)
    participant L1 as Redis L1 Cache (<5ms)
    participant SF as Single-Flight Mutex
    participant DB as PostgreSQL + pgvector
    participant IR as Intent & Shape Router
    participant EMB as Embedding Service
    participant HYB as Hybrid 5-Way Retriever
    participant EXP as Context Expander
    participant RR as Fast Reranker & Diversity
    participant EV as Evidence Evaluator
    participant LLM as Multi-Provider LLM Stream
    participant CS as Citation Sanitizer & Validator

    Client->>API: POST /api/chat/stream {message, convId, filters}
    API->>PG: Evaluate Query Policy
    alt Fast Social Reply / Refusal
        PG-->>API: Action: Social Reply / Fast Refusal
        API-->>Client: Stream SSE (Chunk + Done) & End
    else Passable Query
        PG-->>API: Action: Pass
    end

    API->>L1: Check Exact L1 Match (Key: Query+Lang+Shape+Filter)
    alt L1 Cache Hit (<5ms)
        L1-->>API: Return Cached Answer & Sources
        API-->>Client: Stream SSE (Fast Replay) & End
    else L1 Cache Miss
        L1-->>API: Miss
    end

    API->>SF: Acquire Single-Flight Mutex (Key)
    alt Mutex Not Acquired (Leader Running)
        SF-->>API: Wait & Coalesce on Leader Result
        API-->>Client: Stream SSE (Coalesced Result) & End
    else Mutex Acquired (Leader)
        SF-->>API: Lock Granted
    end

    par Parallel Preparation
        API->>DB: Fetch Active Session State & Recent Turns
        API->>IR: Classify Intent & Resolve Search Query
        API->>EMB: Generate Vector Embedding (768d / 1536d)
    end
    DB-->>API: Prior Turns & Constraints
    IR-->>API: Resolved Query & NeedSearch
    EMB-->>API: Query Vector Values

    alt Needs Search == false (Transform / Clarification)
        API->>LLM: Stream Transform on Prior Turn Content
        LLM-->>Client: Stream SSE Chunks
    else Needs Search == true
        API->>DB: Query L2 Semantic Cache (HNSW Cosine >= 0.87)
        alt L2 Cache Hit (Verified)
            DB-->>API: Cached Validated Answer & Sources
            API->>L1: Populate Redis L1 (24h TTL)
            API-->>Client: Stream SSE & End
        else L2 Cache Miss
            DB-->>API: No Valid Match
        end

        API->>HYB: Execute search_chunks_hybrid(Vector, Text, RRF k=60)
        HYB-->>API: Candidate Chunks (Top 18)
        API->>EXP: Expand Parent Chunks & Group by Page
        EXP-->>API: Rich Grounded Evidence Sources
        API->>RR: Apply Fast Reranking & DiversityGuard
        RR-->>API: Top 6-8 Diverse Evidence Chunks
        API->>EV: Evaluate Evidence Sufficiency
        alt Evidence Inadequate (INSUFFICIENT)
            EV-->>API: Should Abstain (No Solid Proof)
            API-->>Client: Stream Honest Abstention Message & End
        else Evidence Adequate (STRONG / MODERATE)
            EV-->>API: Pass (Grounded)
            API->>LLM: Stream Generation (System Policy + Nonced Evidence + Query)
            loop Streaming Tokens
                LLM-->>API: SSE Chunk Token
                API-->>Client: event: chunk data: {text}
            end
            API->>CS: Align Brackets [1], Strip Phantoms, Audit Entailment
            CS-->>API: Aligned Text & Reconciled Sources
            opt Text or Sources Modified
                API-->>Client: event: text_replace & event: sources
            end
            par Background Tasks
                API->>L1: Save Answer to Redis L1
                API->>DB: Save Answer to L2 Semantic Cache
                API->>DB: Record Chat Message & Extract Memories
                API->>SF: Release Single-Flight Mutex
            end
            API-->>Client: event: done & Close Stream
        end
    end
```

</div>

<div dir="rtl" style="text-align: right; direction: rtl;">

---

### 3. تفصيل مراحل المسار الـ 12 (The 12 Pipeline Stages)

#### المرحلة 1: التدقيق الحتمي الأولي (`PolicyGuard`)
- **الهدف:** فحص السؤال في زمن أقل من `1ms` باستخدام تعبيرات نمطية وقواميس لغوية حتمية معالجة في الذاكرة.
- **التصنيفات:**
  1. `social_reply`: تحيات الإسلام، الترحيب العام، الشكر والثناء، أو السؤال عن الحال. يُعاد الجواب فوراً باللغة المناسبة مع مقترحات أسئلة انطلاق.
  2. `fast_refusal`: أسئلة حية خارجة عن الوثائق (أسعار الذهب، الطقس، الأسهم، الفتاوى الشخصية الحساسة، أو أكواد برمجية عشوائية). يُعتذر للسائل فوراً.
  3. `pass`: سؤال معرفي صالح للبحث؛ يُمرر للمرحلة التالية.

#### المرحلة 2: فحص الكاش السطحي الفوري (`L1 Exact Memory Cache`)
- **الهدف:** البحث في Redis عن تطابق قطعي فوري للأجوبة السابقة.
- **تركيب المفتاح:**
  <div dir="ltr" style="text-align: left; direction: ltr;">
  
  ```text
  rag:l1:{persona}:{lang}:{shape}:{filter_hash}:{sha256(normalized_query)[:24]}
  ```
  </div>
- في حال العثور عليه، يُبث الرد كاملاً في أقل من `5ms` مع انعدام استهلاك أي حصة لنموذج الذكاء الاصطناعي.

#### المرحلة 3: قفل الطيران الفردي الموزع (`Single-Flight Mutex`)
- **الهدف:** منع مشكلة الانهيار المتزامن (Thundering Herd Problem).
- **الآلية:** إذا أرسل 50 مستخدماً نفس السؤال في نفس الثانية، يستحوذ الطلب الأول فقط على قفل Redis (`SET resource NX EX 30`) ليكون "القائد"، بينما تنتظر باقي الطلبات وتستمع لقناة النشر (Pub/Sub) أو استطلاع النتيجة لحظة حفظها، مما يوفر 98% من تكلفة المعالجة.

#### المرحلة 4: المعالجة المتوازية الذكية (Parallel Branching)
- بدلاً من تنفيذ الخطوات بالتسلسل، يُطلق النظام 3 مهام غير متزامنة في نفس اللحظة:
  1. جلب الدورات الحوارية السابقة والذاكرة النشطة للمحادثة من PostgreSQL.
  2. تحليل النية والشكل المطلوب عبر `IntentRouter` لتحديد هل السؤال جديد أم استطرادي أم طلب إعادة صياغة.
  3. توليد المتجه الدلالي للسؤال (`768` بعداً) عبر `EmbeddingService`.

#### المرحلة 5: الكاش الدلالي المتجهي المتطور (`L2 Semantic Cache`)
- **الهدف:** اكتشاف الأسئلة المتطابقة في المعنى والمختلفة في الصياغة اللفظية.
- **البحث:** استعلام فهرس `HNSW` على جدول `semantic_query_cache` مع حصر الفرز بالأبعاد الأربعة (الشخصية، اللغة، شكل الجواب، وبصمة المرشحات).
- **منع الإجابات الزائفة:**
  - إذا كان التشابه الدلالي $\ge 0.97$: يُعتبر تطابقاً تاماً.
  - إذا كان التشابه الدلالي بين $0.87$ و $0.97$: يُستدعى `CacheEquivalenceVerifier` (مع كاش مسبق للثنائيات في Redis) للتحقق مما إذا كان الجواب القديم يكافئ تماماً مقصود السؤال الجديد دون أي تضارب.

#### المرحلة 6: البحث الهجين خماسي المسارات (`5-Way Hybrid RRF Retrieval`)
- استدعاء الدالة المدمجة `search_chunks_hybrid` التي تجمع:
  1. المسار المتجهي: بحث `pgvector` عبر المسافة الكوسينية (`vector_cosine_ops`).
  2. 5 مسارات معجمية: فهارس `GIN` عبر قواميس `arabic`, `simple`, `english`, `spanish`, `portuguese`.
  3. الدمج عبر معادلة:
     $$RRF(d) = \sum_{m \in M} \frac{w_m}{k + \text{rank}_m(d)}, \quad k = 60$$

#### المرحلة 7: توسيع السياق وحل المقاطع الأبوية (`ContextExpander`)
- المقاطع المسترجعة هي مقاطع فرعية (`CHILD Chunks ~280t`).
- يقوم المحرك بجلب المقاطع الأبوية الشاملة (`PARENT Chunks ~1000t`) دفعة واحدة بطلب SQL ذري (`id = ANY($1::uuid[])`).
- يتم تجميع المقاطع المتعددة التابعة لنفس الصفحة أو الفصل في بطاقة مرجعية واحدة لتفادي تكرار البطاقات في واجهة المستخدم.

#### المرحلة 8: إعادة الترتيب الحتمي وتنوع المصادر (`Reranker & DiversityGuard`)
- تطبيق خوارزمية الترتيب الحتمية السريعة في الميكروثانية بناءً على تطابق العبارة ونسبة تغطية المصطلحات وتشابه المتجه.
- تطبيق `DiversityGuard`: حظر استئثار فصل أو كتاب واحد بأكثر من مقطعين (`maxPerBook=2`) لضمان تنوع الأدلة وشموليتها.

#### المرحلة 9: تقييم كفاية الأدلة والامتناع الصريح (`EvidenceEvaluator`)
- فحص درجات التشابه والرتبة؛ فإذا كان السند ضعيفاً جداً (`similarity < 0.35` وانعدام التطابق المعجمي)، يمتنع المحرك فوراً عن استدعاء نموذج التوليد ويرسل رسالة اعتذار رصينة تثبت أمانة النظام وعدم تلفيقه للبيانات.

#### المرحلة 10: بناء السياق الآمن وبث التوليد اللحظي (`Adaptive Context & SSE`)
- يوزع `AdaptiveContextManager` ميزانية التوكنز بدقة (تعليمات النظام $\to$ الذاكرة $\to$ ملخص الدورات $\to$ الأدلة المسترجعة $\to$ السؤال).
- تسييج الأدلة برمز عشوائي (`Cryptographic Nonce`) يمنع تجاوز تعليمات النظام.
- بدء البث المباشر للأحرف والكلمات عبر بروتوكول Server-Sent Events (SSE) باستخدام نموذج `Gemini 3.5`، مع مراقبة مبكرة لأول 100 حرف لمنع انحراف اللغة الهدف (`Language Drift Guard`).

#### المرحلة 11: تدقيق الاستشهادات وتحقيق الاستلزام (`Citation Alignment & Entailment`)
- فور انتهاء البث، يتدخل `CitationSanitizer`:
  - تحويل الأرقام المشرقية `[١]` إلى أرقام قياسية `[1]`.
  - حذف أرقام المراجع الشبحية (مثل ورود `[9]` بينما المراجع المتاحة 4 فقط).
  - إعادة فهرسة الأقواس تسلسلياً (مثلاً: إذا استشهد الجواب بـ `[3, 4]` فقط، تصبح في النص `[1, 2]` وتُطابق قائمة المصادر).
  - حساب نسبة الاستلزام المعجمي (`claimEntailmentScore`) بين كل ادعاء والمقطع المحال إليه.

#### المرحلة 12: الحفظ المتزامن والمقترحات والذاكرة (Post-Processing & Telemetry)
- حفظ الجواب في كاش L1 (Redis) لمدة 24 ساعة.
- حفظ الجواب في كاش L2 (pgvector) مع تدقيق التوثيق الكامل لمدة 7 أيام.
- استخراج الحقائق والقرارات الحوارية وتحديث حالة الجلسة (`Session State`).
- توليد أسئلة تتبعية مقترحة مبنية على محتوى الإجابة الدقيقة.
- إرسال حدث النهاية `event: done` وإغلاق تدفق SSE بأمان.

</div>
