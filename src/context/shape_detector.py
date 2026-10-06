"""Shape-adaptive prompting: detects structural intent and injects directive prompts."""

from dataclasses import dataclass
import re
from typing import Dict

TABLE_REGEX = re.compile(r"\b(جدول|في جدول|صفوف وأعمدة|مصفوفة|table|in a table|tabular)\b", re.IGNORECASE)
COMPARISON_REGEX = re.compile(r"\b(قارن بين|ما الفرق بين|أوجه الشبه|أوجه الاختلاف|مقارنة منهجية|compare|contrast|difference between)\b", re.IGNORECASE)
STEPS_REGEX = re.compile(r"\b(خطوات|مراحل|كيف أقوم|طريقة عمل|إجراءات|steps|phases|procedure|how do i|how to)\b", re.IGNORECASE)
DEFINITION_REGEX = re.compile(r"\b(عرف|ما مفهوم|ما معنى|ما هو باختصار|تعريف مركز|define|definition|what is the meaning of|briefly define)\b", re.IGNORECASE)
IN_DEPTH_REGEX = re.compile(r"\b(بحث مستفيض|تأصيل عميق|استقصاء|دراسة شاملة|تحليل مفصل|in depth|detailed study|comprehensive analysis)\b", re.IGNORECASE)

SHAPE_DIRECTIVES: Dict[str, Dict[str, str]] = {
    "markdown_table": {
        "ar": "التزم بصياغة الإجابة في جدول Markdown متكامل يحتوي ترويسة واضحة وأعمدة متناسقة، مع إبقاء أرقام الاستشهادات [1] داخل الخلايا المعنية.",
        "en": "Format your answer strictly as a clean Markdown table with descriptive headers and columns. Keep citation indices [1] inside the corresponding table cells.",
    },
    "comparison": {
        "ar": "أنشئ مقارنة منهجية ودقيقة توضح أوجه الاتفاق والافتراق بين المسائل أو المصادر، مع دعم كل نقطة بالاستشهادات المرجعية.",
        "en": "Provide a structured, methodical comparison detailing points of agreement and contrast, supported with exact citations.",
    },
    "procedural_steps": {
        "ar": "رتب الإجابة في خطوات أو مراحل إجرائية متسلسلة ومرقمة (1، 2، 3) مع بيان دليل أو ضابط كل خطوة بوضوح.",
        "en": "Structure your response into numbered, logical sequential steps (1, 2, 3), detailing the rationale and evidence for each step.",
    },
    "short_definition": {
        "ar": "قدم تعريفاً جامعاً مانعاً ومركزاً في فقرة واحدة مباشرة دون استطراد زائد.",
        "en": "Provide a concise, precise definition in a single focused paragraph without unnecessary digressions.",
    },
    "in_depth_investigation": {
        "ar": "استعرض المسألة بأبعادها المنهجية والتأصيلية بتحقيق علمي مستفيض مع استيعاب وتوثيق كافة الأدلة المتاحة.",
        "en": "Conduct an in-depth, thorough investigation covering all methodological dimensions and rigorously citing all available evidence.",
    },
    "standard": {
        "ar": "أجب بأسلوب منهجي موثق وموضوعي مستنداً حصراً إلى الأدلة المعرفية المتاحة.",
        "en": "Provide a well-structured, objective response grounded strictly in the provided evidence.",
    },
}


@dataclass
class ShapeResult:
    """Detected shape and corresponding system directive."""

    shape: str
    directive: str


class ShapeDetector:
    """Detects requested output shape and returns localized system directives."""

    def detect_shape(self, query: str, lang: str = "ar") -> ShapeResult:
        """Determines the desired shape based on semantic indicators in the user query."""
        raw = query.strip()
        target_lang = "ar" if lang.startswith("ar") else "en"

        if TABLE_REGEX.search(raw):
            shape = "markdown_table"
        elif COMPARISON_REGEX.search(raw):
            shape = "comparison"
        elif STEPS_REGEX.search(raw):
            shape = "procedural_steps"
        elif DEFINITION_REGEX.search(raw):
            shape = "short_definition"
        elif IN_DEPTH_REGEX.search(raw):
            shape = "in_depth_investigation"
        else:
            shape = "standard"

        directive = SHAPE_DIRECTIVES[shape].get(target_lang, SHAPE_DIRECTIVES[shape]["en"])
        return ShapeResult(shape=shape, directive=directive)
