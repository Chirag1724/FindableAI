"""Intelligence engines package."""

from .contradiction import (
    ContradictionDetectionError,
    ContradictionDetector,
    detect_contradictions,
)
from .entailment_engine import (
    EntailmentEngine,
    EntailmentError,
    evaluate_intent,
    evaluate_intents,
)
from .intent_generator import IntentGenerationError, IntentGenerator, generate_intents
from .jsonld_generator import JsonLdGenerator, JsonLdGeneratorError, generate_jsonld
from .patch_formatter import PatchFormatter, PatchFormatterError, format_patches
from .patch_prioritizer import (
    PatchPrioritizer,
    PatchPrioritizerError,
    calculate_priority,
    prioritize,
)
from .projected_score import (
    ProjectedScoreCalculator,
    ProjectedScoreError,
    project_score_for_generated,
    project_scores,
)
from .lighthouse import LighthouseEngine
from .llms_txt_generator import generate_llms_full_txt, generate_llms_txt
from .robots_analyzer import (
    analyze_robots_txt,
    classify_scraping_risk,
    compute_ai_visibility_index,
    extract_features,
    generate_optimized_robots_txt,
)
from .scorer import ScoreInputs, Scorer, ScorerError, score

__all__ = [
    "ContradictionDetectionError",
    "ContradictionDetector",
    "EntailmentEngine",
    "EntailmentError",
    "IntentGenerationError",
    "IntentGenerator",
    "JsonLdGenerator",
    "JsonLdGeneratorError",
    "LighthouseEngine",
    "PatchFormatter",
    "PatchFormatterError",
    "PatchPrioritizer",
    "PatchPrioritizerError",
    "ProjectedScoreCalculator",
    "ProjectedScoreError",
    "ScoreInputs",
    "Scorer",
    "ScorerError",
    "analyze_robots_txt",
    "calculate_priority",
    "classify_scraping_risk",
    "compute_ai_visibility_index",
    "detect_contradictions",
    "evaluate_intent",
    "evaluate_intents",
    "extract_features",
    "format_patches",
    "generate_intents",
    "generate_jsonld",
    "generate_llms_full_txt",
    "generate_llms_txt",
    "generate_optimized_robots_txt",
    "prioritize",
    "project_score_for_generated",
    "project_scores",
    "score",
]
