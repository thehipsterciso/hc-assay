"""Reasoning seam — the single abstraction over LLM execution by stakes tier.

No engine component talks to an LLM directly. The seam routes by *stakes*: a local model for
bulk/low-stakes work, a frontier model via a fixed-cost subscription path for high-stakes
work (no metered API — ADR-0003). It owns timeouts, retries, credential scrubbing, and
tracing. Ported and generalized from the prior platform's hardened ``reasoning_client``.

Heavy backends are optional (the ``reasoning`` extra); the module imports without them.
"""

from assay_engine.reasoning.seam import (
    PermanentReasoningError,
    RateLimitError,
    ReasoningError,
    ReasoningRequest,
    ReasoningSeam,
    StakesTier,
    TieredReasoningSeam,
    UnconfiguredReasoningSeam,
    extract_json,
    is_metered_anthropic_credential,
    scrubbed_env,
)

__all__ = [
    "PermanentReasoningError",
    "RateLimitError",
    "ReasoningError",
    "ReasoningRequest",
    "ReasoningSeam",
    "StakesTier",
    "TieredReasoningSeam",
    "UnconfiguredReasoningSeam",
    "extract_json",
    "is_metered_anthropic_credential",
    "scrubbed_env",
]
