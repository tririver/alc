"""Durable scientific translation workflows."""

__version__ = "2.0.5"

from .atoms import (
    PROTECTED_ATOM_PLAN_SCHEMA,
    PROTECTED_ATOM_RESULT_SCHEMA,
)
from .contracts import (
    GLOSSARY_FALLBACK_SUMMARY_SCHEMA,
    GLOSSARY_RESULT_SCHEMA,
    LANGUAGE_RESULT_SCHEMA,
    TRANSLATION_RESULT_SCHEMA,
    BlocksRequest,
    ExecutionOptions,
    GenerationRecipe,
    GlossaryRequest,
    LanguageRequest,
    TranslationSource,
)
from .handlers import (
    BLOCKS_HANDLER,
    GLOSSARY_HANDLER,
    LANGUAGE_HANDLER,
    BuildGlossaryHandler,
    DetectLanguageHandler,
    TranslateBlocksHandler,
)
from .project import (
    PROJECT_SCHEMA,
    TranslationProject,
    TranslationProjectError,
)
from .service import TranslationService, TranslationServiceError
from .source import (
    TranslationSourceError,
    canonicalize_translation_markdown,
    deterministic_language_samples,
    resolve_translation_source,
    same_primary_language,
    source_blocks,
    validate_translation_markdown,
)
from .workflow import (
    REVIEW_SUPERVISION_SCHEMA,
    GlossaryFallbackSummary,
    GlossaryResult,
    KeywordProvider,
    LanguageResult,
    TranslationResult,
    TranslationRevisionArtifact,
    TranslationWorkflowError,
    TranslationWorkflowService,
)

__all__ = [
    "BLOCKS_HANDLER",
    "GLOSSARY_FALLBACK_SUMMARY_SCHEMA",
    "GLOSSARY_HANDLER",
    "GLOSSARY_RESULT_SCHEMA",
    "LANGUAGE_HANDLER",
    "LANGUAGE_RESULT_SCHEMA",
    "PROJECT_SCHEMA",
    "PROTECTED_ATOM_PLAN_SCHEMA",
    "PROTECTED_ATOM_RESULT_SCHEMA",
    "REVIEW_SUPERVISION_SCHEMA",
    "TRANSLATION_RESULT_SCHEMA",
    "BlocksRequest",
    "BuildGlossaryHandler",
    "DetectLanguageHandler",
    "ExecutionOptions",
    "GenerationRecipe",
    "GlossaryFallbackSummary",
    "GlossaryRequest",
    "GlossaryResult",
    "KeywordProvider",
    "LanguageRequest",
    "LanguageResult",
    "TranslateBlocksHandler",
    "TranslationProject",
    "TranslationProjectError",
    "TranslationResult",
    "TranslationRevisionArtifact",
    "TranslationService",
    "TranslationServiceError",
    "TranslationSource",
    "TranslationSourceError",
    "TranslationWorkflowError",
    "TranslationWorkflowService",
    "canonicalize_translation_markdown",
    "deterministic_language_samples",
    "resolve_translation_source",
    "same_primary_language",
    "source_blocks",
    "validate_translation_markdown",
]
