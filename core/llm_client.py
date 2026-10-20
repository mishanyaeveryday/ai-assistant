import asyncio

import openai
from openai import AsyncOpenAI

# Waits between attempts when the model is overloaded (5xx) or rate limited
# (429). Those come and go within seconds, and failing on the first one would
# throw away a task that may be many tool calls in.
RETRY_DELAYS_SECONDS = (2, 5, 10)


# A rate limit that lifts later than this is a used-up quota (free models
# allow a fixed number of requests per day), and waiting would only stall.
MAX_RETRY_AFTER_SECONDS = 30


class EmptyResponseError(Exception):
    """OpenRouter answered, but with no choice in it - the provider behind it
    failed mid-way. Worth another attempt, like a 5xx."""


def _retry_after_seconds(error: Exception) -> float | None:
    """The wait the API asked for in its Retry-After header."""
    response = getattr(error, "response", None)
    value = response.headers.get("retry-after") if response is not None else None
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


def _is_transient(error: Exception) -> bool:
    if isinstance(error, (openai.InternalServerError, openai.APIConnectionError,
                          EmptyResponseError)):
        return True
    if not isinstance(error, openai.RateLimitError):
        return False
    retry_after = _retry_after_seconds(error)
    return retry_after is None or retry_after <= MAX_RETRY_AFTER_SECONDS


class LLMClient:
    """Chat completions through OpenRouter, so any model it lists can be used."""

    def __init__(self, llm_model, api_key, base_url, fallback_models=()):
        if not api_key:
            raise RuntimeError(
                "OPENROUTER_API_KEY is not set - add it to .env "
                "(get a key at https://openrouter.ai/keys)")
        self.llm_model = llm_model
        self.fallback_models = list(fallback_models)
        # The retries are done in generate(), which tells a used-up quota from
        # a short spike; the SDK's own would stack on top of them.
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url, max_retries=0)

    async def generate(self, messages, tools, temperature):
        """Returns the reply message: its text, or the tools it wants called."""
        request = dict(model=self.llm_model, messages=messages, temperature=temperature)
        if tools:
            request["tools"] = tools
        if self.fallback_models:
            request["extra_body"] = {"models": [self.llm_model, *self.fallback_models]}

        for attempt, delay in enumerate((*RETRY_DELAYS_SECONDS, None)):
            try:
                response = await self.client.chat.completions.create(**request)
                if not response.choices:
                    raise EmptyResponseError(
                        getattr(response, "error", None) or "the model returned no reply")
                return response.choices[0].message
            except Exception as e:
                if delay is None or not _is_transient(e):
                    print("The error is: ", e)
                    raise
                print(f"[LLM] {e.__class__.__name__} {getattr(e, 'status_code', '')}, "
                      f"retrying in {delay}s (attempt {attempt + 2})")
                await asyncio.sleep(delay)
