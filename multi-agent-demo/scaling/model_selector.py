"""Fallback model chain with automatic selection and override support."""

import os
import logging

from scaling.config import MODEL_CHAIN

logger = logging.getLogger(__name__)


def get_model(agent_name: str = "", attempt: int = 0) -> str:
    """Return the model to use based on attempt number and overrides.

    - MODEL_OVERRIDE env var forces a specific model for all agents.
    - Otherwise, walks the MODEL_CHAIN based on the attempt number.
    """
    override = os.getenv("MODEL_OVERRIDE")
    if override:
        logger.info(f"[model_selector] {agent_name}: using override model '{override}'")
        return override

    index = min(attempt, len(MODEL_CHAIN) - 1)
    model = MODEL_CHAIN[index]
    if attempt > 0:
        logger.info(f"[model_selector] {agent_name}: fallback attempt {attempt}, using '{model}'")
    else:
        logger.info(f"[model_selector] {agent_name}: using '{model}'")
    return model
