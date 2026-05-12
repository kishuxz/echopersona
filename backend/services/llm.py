import asyncio
from collections.abc import AsyncGenerator

from config import settings


DEFAULT_SYSTEM_PROMPT = (
    "You are EchoPersona, a low-latency conversational voice avatar. "
    "Answer naturally in 2 short sentences."
)


async def _mock_stream_llm(user_message: str) -> AsyncGenerator[str, None]:
    response = (
        "I heard you clearly. The first complete sentence is sent to voice immediately."
    )
    if user_message:
        response = f"You said: {user_message}. " + response
    for token in response.split(" "):
        await asyncio.sleep(0.004)
        yield token + " "


async def stream_llm(
    user_message: str,
    system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    conversation_history: list[dict] | None = None,
) -> AsyncGenerator[str, None]:
    """
    Stream LLM tokens from Groq or an OpenAI-compatible vLLM endpoint.
    Falls back to a local deterministic stream when API keys are absent.
    """
    conversation_history = conversation_history or []
    if settings.mock_mode and not settings.use_vllm:
        async for token in _mock_stream_llm(user_message):
            yield token
        return

    messages = [
        {"role": "system", "content": system_prompt},
        *conversation_history[-6:],
        {"role": "user", "content": user_message},
    ]

    if settings.use_vllm:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key="local", base_url=settings.vllm_base_url)
        stream = await client.chat.completions.create(
            model="meta-llama/Llama-3.3-70B-Instruct",
            messages=messages,
            max_tokens=300,
            temperature=0.7,
            stream=True,
        )
    else:
        from groq import AsyncGroq, BadRequestError, RateLimitError

        client = AsyncGroq(api_key=settings.groq_api_key)
        # Ordered by latency on Groq as of 2025-05.
        # specdec/mixtral/gemma2 are decommissioned; compound-mini is ~1s TTFT.
        _models = [
            "llama-3.1-8b-instant",                        # Most consistent, ~160-280ms
            "meta-llama/llama-4-scout-17b-16e-instruct",  # Better quality, variable latency
            "llama-3.3-70b-versatile",                     # Last resort, higher latency
        ]
        stream = None
        for model in _models:
            try:
                stream = await client.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_tokens=80,
                    temperature=0.7,
                    top_p=0.9,
                    stream=True,
                )
                print(f"[LLM] using model: {model}")
                break
            except RateLimitError:
                print(f"[LLM] {model} rate limited, trying next")
                continue
            except BadRequestError as e:
                print(f"[LLM] {model} bad request ({e}), trying next")
                continue
        else:
            raise RuntimeError("All LLM models unavailable (rate limited or decommissioned)")

    async for chunk in stream:
        token = chunk.choices[0].delta.content
        if token:
            yield token
