"""Chat model used by the agent.

The provider is configuration, not code. ``init_chat_model`` accepts a
``provider:model`` spec and reads the corresponding credential from the
environment, so switching between providers is an ``.env`` change and the rest
of the application never imports a provider SDK (AGENTS.MD §9).

Resolution order, from most to least explicit:

1. ``AGENT_MODEL`` — the canonical setting, e.g. ``anthropic:claude-opus-5``;
2. ``OPENAI_MODEL`` — the name used by ``SPEC.md``, read as ``openai:<model>``
   so existing ``.env`` files keep working;
3. :data:`DEFAULT_AGENT_MODEL`.
"""

from __future__ import annotations

import logging

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from app.config import settings
from app.errors import ConfigurationError

logger = logging.getLogger(__name__)

#: Used when nothing is configured. Anthropic is the default because
#: ``deepagents`` already depends on ``langchain-anthropic``: it is the one
#: provider guaranteed to be installed.
DEFAULT_AGENT_MODEL = "anthropic:claude-opus-5"
SUPPORTED_MODEL_PROVIDERS = frozenset({"anthropic", "openai"})


def resolve_model_spec() -> str:
    """Return the ``provider:model`` spec the agent should run on."""

    if settings.agent_model:
        resolved = settings.agent_model
    elif settings.openai_model:
        resolved = f"openai:{settings.openai_model}"
    else:
        resolved = DEFAULT_AGENT_MODEL
    _validate_model_spec(resolved)
    return resolved


def create_chat_model(
    spec: str | None = None, *, timeout: float | None = None, max_retries: int | None = None
) -> BaseChatModel:
    """Build the chat model, turning a provider problem into a domain error.

    A missing API key or an uninstalled provider package raises from deep
    inside LangChain. Translating it here means the caller sees the same
    ``ConfigurationError`` it already handles for Notion, with a message that
    names the setting to fix and never the credential itself.
    """

    resolved = spec or resolve_model_spec()
    _validate_model_spec(resolved)
    logger.info("agent.model.resolved", extra={"model": resolved})
    try:
        options = {}
        if timeout is not None:
            options["timeout"] = timeout
        if max_retries is not None:
            options["max_retries"] = max_retries
        model = init_chat_model(resolved, **options)
    except Exception as exc:  # any provider failure is a configuration problem
        raise ConfigurationError(
            f"The agent model {resolved!r} could not be initialized. Check AGENT_MODEL "
            f"and the credential required by the provider."
        ) from exc
    if not isinstance(model, BaseChatModel):  # pragma: no cover - configurable specs
        raise ConfigurationError(
            f"The agent model {resolved!r} resolved to a configurable model. "
            f"Use a concrete 'provider:model' spec."
        )
    return model


def _validate_model_spec(spec: str) -> None:
    provider, separator, model = spec.partition(":")
    if (
        separator != ":"
        or not provider
        or not model
        or ":" in model
        or provider not in SUPPORTED_MODEL_PROVIDERS
    ):
        supported = ", ".join(sorted(SUPPORTED_MODEL_PROVIDERS))
        raise ConfigurationError(
            "AGENT_MODEL must use a concrete 'provider:model' spec from the "
            f"supported providers: {supported}."
        )
