"""Reasoning seam — the single abstraction over LLM execution by stakes tier.

No engine component talks to an LLM directly. The seam routes by *stakes*: a local model for
bulk/low-stakes work, a frontier model via a fixed-cost subscription path for high-stakes
work (no metered API — ADR-0003). It owns timeouts, retries, and tracing.

To be lifted and generalized from the prior platform's hardened ``reasoning_client``.
"""

from assay_engine.reasoning.seam import ReasoningRequest, ReasoningSeam, StakesTier

__all__ = ["ReasoningRequest", "ReasoningSeam", "StakesTier"]
