<div dir="rtl" style="text-align: right; direction: rtl;">

# ⚙️ التكوين والإعدادات والمتغيرات البيئية (System Configuration & Environment Variables)
## الدليل التشغيلي الشامل لمفاتيح التكوين، نماذج Pydantic Settings، والقيم الافتراضية

---

### 1. فلسفة التكوين أولاً (Configuration-First Design)

تم تصميم هذا المخطط ليكون قابلاً للتخصيص الكامل دون الحاجة إلى تعديل الكود المصدري.
تتم قراءة كافة الإعدادات والتحقق من صحتها في لحظة إقلاع التطبيق (Startup Time) باستخدام **Pydantic Settings v2**.
إذا كان هناك أي متغير إلزامي مفقود أو ذو قيمة غير صالحة، يفشل النظام في الإقلاع فوراً مع رسالة خطأ واضحة وصريحة (**Fail-Fast Principle**)، مما يمنع حدوث أخطاء تشغيلية غير متوقعة في وقت لاحق.

---

### 2. جدول المتغيرات البيئية الشامل (Complete Environment Variables Matrix)

| اسم المتغير البيئي (Environment Variable) | النوع (Type) | القيمة الافتراضية (Default) | الوصف الهندسي والتأثير |
| :--- | :---: | :---: | :--- |
| **`ENVIRONMENT`** | `str` | `production` | بيئة التشغيل (`development`, `staging`, `production`, `test`). |
| **`LOG_LEVEL`** | `str` | `INFO` | مستوى السجلات المهيكلة (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |
| **`DATABASE_URL`** | `str` | *إلزامي* | رابط اتصال PostgreSQL بصيغة `postgresql+asyncpg://...`. |
| **`DATABASE_POOL_SIZE`** | `int` | `20` | عدد اتصالات حوض SQLAlchemy الدائمة. |
| **`DATABASE_MAX_OVERFLOW`** | `int` | `10` | أقصى اتصالات إضافية مؤقتة عند ذروة الطلب. |
| **`REDIS_URL`** | `str` | `redis://localhost:6379/0` | رابط اتصال خادم Redis للكاش وقفل الطيران الفردي. |
| **`DEFAULT_CHAT_MODEL`** | `str` | `gemini-3.5-flash-lite` | نموذج التوليد الافتراضي (تجنب `gemini-2.5-flash` لعدم دعمه). |
| **`DEFAULT_FALLBACK_MODEL`** | `str` | `gemini-1.5-flash` | نموذج الطوارئ البديل في حال تعثر النموذج الأساسي. |
| **`DEFAULT_EMBEDDING_MODEL`** | `str` | `gemini-embedding-2` | نموذج التضمين المتجهي الافتراضي للوثائق والأسئلة. |
| **`EMBEDDING_DIMENSION`** | `int` | `768` | بعد المتجه الدلالي المطابق لفهارس HNSW. |
| **`SEMANTIC_CACHE_SIMILARITY_THRESHOLD`**| `float` | `0.87` | أدنى عتبة تشابه للنظر في مرشحي كاش pgvector. |
| **`SEMANTIC_CACHE_DIRECT_HIT_THRESHOLD`**| `float` | `0.97` | عتبة التطابق القطعي الفوري دون الحاجة لمدقق التكافؤ. |
| **`SEMANTIC_CACHE_VERIFIER_ENABLED`** | `bool` | `true` | تفعيل مدقق التكافؤ التام للنطاق الحرج ($0.87 - 0.97$). |
| **`SEMANTIC_CACHE_TTL_DAYS`** | `int` | `7` | مدة بقاء السجلات في كاش L2 المتجهي. |
| **`L1_REDIS_CACHE_TTL_SECONDS`** | `int` | `86400` | مدة بقاء الاستجابات السطحية في Redis L1 (24 ساعة). |
| **`CHUNKER_MAX_TOKENS`** | `int` | `280` | الحجم الأقصى المستهدف للمقاطع الفرعية (Child Chunks). |
| **`CHUNKER_OVERLAP_TOKENS`** | `int` | `50` | تداخل الرموز بين المقاطع الفرعية المتتالية لحفظ السياق. |
| **`PARENT_SECTION_MAX_TOKENS`** | `int` | `1000` | الحجم الأقصى للمقاطع الأبوية السياقية (Parent Sections). |
| **`RRF_K_CONSTANT`** | `float` | `60.0` | ثابت التنعيم لخوارزمية دمج الرتب المتبادلة RRF. |
| **`RETRIEVAL_TOP_K`** | `int` | `8` | عدد المقاطع النهائية الممررة للنموذج اللغوي بعد الترتيب. |
| **`DIVERSITY_MAX_PER_BOOK`** | `int` | `2` | أقصى عدد مقاطع مسموح به من نفس الكتاب/الفصل لمنع الاحتكار. |
| **`CHAT_TARGET_INPUT_BUDGET`** | `int` | `12000` | الميزانية المستهدفة لمدخلات البرومبت. |
| **`CHAT_HARD_MAX_INPUT`** | `int` | `16384` | السقف الصلب الذي يُمنع تجاوزه لمدخلات النموذج. |
| **`CHAT_MAX_OUTPUT_TOKENS`** | `int` | `8192` | السقف الأقصى لتوليد الإجابة بالبث المباشر. |
| **`RATE_LIMIT_USER_RPM`** | `int` | `120` | أقصى طلبات مسموح بها في الدقيقة للمستخدم المسجل. |
| **`RATE_LIMIT_GUEST_RPM`** | `int` | `15` | أقصى طلبات مسموح بها في الدقيقة للزائر غير المسجل. |

---

### 3. متغيرات خزنة المفاتيح المموهة (Deceptive KeyVault Slices)

| اسم المتغير البيئي (Key Slice) | الجزء المخزن | الترتيب في `.env` |
| :--- | :---: | :---: |
| **`TadabburApiKey`** (أو `MidadeApiKey`) | الجزء الأول (1/3) | يظهر أولاً في السطر 1. |
| **`ApiSalt`** | الجزء الثالث (3/3) | يظهر ثانياً في السطر 2 للتمويه والتضليل. |
| **`ApiSecret`** | الجزء الثاني (2/3) | يظهر ثالثاً في السطر 3. |
| **`GEMINI_API_KEY`** | المفتاح الصريح | بديل اختياري لبيئات التطوير المحلي فقط. |

---

### 4. فئة الإعدادات البرمجية (`src/core/config.py`)

<div dir="ltr" style="text-align: left; direction: ltr;">

```python
from pydantic import Field, PostgresDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Environment & Application Identity
    environment: str = Field(default="production", env="ENVIRONMENT")
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    cors_origins: list[str] = Field(default=["*"], env="CORS_ORIGINS")

    # Database Persistence
    database_url: PostgresDsn = Field(..., env="DATABASE_URL")
    database_pool_size: int = Field(default=20, env="DATABASE_POOL_SIZE")
    database_max_overflow: int = Field(default=10, env="DATABASE_MAX_OVERFLOW")

    # Redis Cache & Broker
    redis_url: RedisDsn = Field(default="redis://localhost:6379/0", env="REDIS_URL")

    # LLM & Embedding Models
    default_chat_model: str = Field(default="gemini-3.5-flash-lite", env="DEFAULT_CHAT_MODEL")
    default_fallback_model: str = Field(default="gemini-1.5-flash", env="DEFAULT_FALLBACK_MODEL")
    default_embedding_model: str = Field(default="gemini-embedding-2", env="DEFAULT_EMBEDDING_MODEL")
    embedding_dimension: int = Field(default=768, env="EMBEDDING_DIMENSION")

    # Deceptive Key Vault Partitions
    api_key_part1: Optional[str] = Field(default=None, env="TadabburApiKey")
    api_key_part2: Optional[str] = Field(default=None, env="ApiSecret")
    api_key_part3: Optional[str] = Field(default=None, env="ApiSalt")
    gemini_api_key_direct: Optional[str] = Field(default=None, env="GEMINI_API_KEY")

    # Retrieval & RRF Tuning
    rrf_k_constant: float = Field(default=60.0, env="RRF_K_CONSTANT")
    retrieval_top_k: int = Field(default=8, env="RETRIEVAL_TOP_K")
    diversity_max_per_book: int = Field(default=2, env="DIVERSITY_MAX_PER_BOOK")

    # Semantic Cache Multi-Dimensional Scoping
    semantic_cache_similarity_threshold: float = Field(default=0.87, env="SEMANTIC_CACHE_SIMILARITY_THRESHOLD")
    semantic_cache_direct_hit_threshold: float = Field(default=0.97, env="SEMANTIC_CACHE_DIRECT_HIT_THRESHOLD")
    semantic_cache_verifier_enabled: bool = Field(default=True, env="SEMANTIC_CACHE_VERIFIER_ENABLED")
    semantic_cache_ttl_days: int = Field(default=7, env="SEMANTIC_CACHE_TTL_DAYS")
    l1_redis_cache_ttl_seconds: int = Field(default=86400, env="L1_REDIS_CACHE_TTL_SECONDS")

    # Ingestion & Chunking
    chunker_max_tokens: int = Field(default=280, env="CHUNKER_MAX_TOKENS")
    chunker_overlap_tokens: int = Field(default=50, env="CHUNKER_OVERLAP_TOKENS")
    parent_section_max_tokens: int = Field(default=1000, env="PARENT_SECTION_MAX_TOKENS")

    # Context & Token Budgeting
    chat_target_input_budget: int = Field(default=12000, env="CHAT_TARGET_INPUT_BUDGET")
    chat_hard_max_input: int = Field(default=16384, env="CHAT_HARD_MAX_INPUT")
    chat_max_output_tokens: int = Field(default=8192, env="CHAT_MAX_OUTPUT_TOKENS")

settings = AppSettings()
```

</div>
