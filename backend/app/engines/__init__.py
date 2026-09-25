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
    "PatchFormatter",
    "PatchFormatterError",
    "PatchPrioritizer",
    "PatchPrioritizerError",
    "ProjectedScoreCalculator",
    "ProjectedScoreError",
    "ScoreInputs",
    "Scorer",
    "ScorerError",
    "calculate_priority",
    "detect_contradictions",
    "evaluate_intent",
    "evaluate_intents",
    "format_patches",
    "generate_intents",
    "generate_jsonld",
    "prioritize",
    "project_score_for_generated",
    "project_scores",
    "score",
]
