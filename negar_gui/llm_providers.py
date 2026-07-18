import logging
import re

import requests

POLLINATIONS_URL = "https://text.pollinations.ai/openai"

PROMPTS = {
    "fix_grammar": {
        "name": "Fix Grammar",
        "system_prompt": "You are an expert Persian editor and proofreader. Correct grammar, spelling, punctuation, and نیم‌فاصله according to the Academy of Persian Language and Literature. Preserve the author's tone and meaning. Return only the final corrected text.",
        "prefix": "متن زیر را ویرایش کن: ",
    },
}

logger = logging.getLogger(__name__)


def fix_text(text: str, prompt_key: str = "fix_grammar") -> str:
    if not text.strip():
        return text

    prompt = PROMPTS.get(prompt_key)
    if not prompt:
        return text

    max_tokens = max(256, len(f"{prompt['prefix']}{text}") * 2)

    payload = {
        "model": "openai",
        "messages": [
            {"role": "system", "content": prompt["system_prompt"]},
            {"role": "user", "content": f"{prompt['prefix']}{text}"},
        ],
        "temperature": 0.0,
        "max_tokens": max_tokens,
    }

    try:
        resp = requests.post(POLLINATIONS_URL, json=payload, timeout=60)
        resp.raise_for_status()
        msg = resp.json()["choices"][0]["message"]
        result = (msg.get("content") or msg.get("reasoning") or "").strip()
        if not result:
            raise KeyError("content")
        m = re.search(r"<corrected\s*text>(.*?)</corrected\s*text>", result, re.DOTALL)
        if m:
            result = m.group(1).strip()
        return result
    except requests.RequestException as e:
        logger.error("LLM request failed: %s", e)
        raise RuntimeError(f"LLM request failed: {e}") from e
