"""What OpenRouter offers, from its public model list - reading it needs no
key and costs nothing."""
import httpx

from config.settings import OPENROUTER_BASE_URL

MODELS_TIMEOUT_SECONDS = 15


async def fetch_models(transport: httpx.AsyncBaseTransport | None = None) -> list[dict]:
    """Every model OpenRouter lists, as it describes them."""
    async with httpx.AsyncClient(timeout=MODELS_TIMEOUT_SECONDS, transport=transport) as client:
        response = await client.get(f"{OPENROUTER_BASE_URL}/models")
        response.raise_for_status()
    return response.json().get("data") or []


async def fetch_tool_models(transport: httpx.AsyncBaseTransport | None = None) -> list[str]:
    """Ids of the models that can call tools. The assistant offers the model
    tools on every prompt, and one that cannot take them fails. Sorted, so a
    vendor's models sit together."""
    models = await fetch_models(transport)
    return sorted({model["id"] for model in models
                   if model.get("id") and "tools" in (model.get("supported_parameters") or [])})


def accepts_images(models: list[dict], model_id: str) -> bool | None:
    """Whether the model takes images as input, or None if OpenRouter does
    not list it."""
    for model in models:
        if model.get("id") == model_id:
            modalities = (model.get("architecture") or {}).get("input_modalities") or []
            return "image" in modalities
    return None
