import logging
import re

import requests

POLLINATIONS_URL = "https://text.pollinations.ai/openai"

# All of these speak the OpenAI chat-completions format; only URL, model and key differ.
PROVIDERS = {
    "pollinations": {
        "name": "Pollinations (no key, rate-limited)",
        "url": POLLINATIONS_URL,
        "model": "openai",
        "key_url": "",
    },
    "gemini": {
        "name": "Google Gemini (free key)",
        "url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "model": "gemini-3.5-flash-lite",
        "key_url": "https://aistudio.google.com/apikey",
    },
    "groq": {
        "name": "Groq (free key)",
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "model": "openai/gpt-oss-120b",
        "key_url": "https://console.groq.com/keys",
    },
    "openrouter": {
        "name": "OpenRouter (free key)",
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "model": "openrouter/free",
        "key_url": "https://openrouter.ai/settings/keys",
    },
    "openai": {
        "name": "OpenAI (paid key)",
        "url": "https://api.openai.com/v1/chat/completions",
        "model": "gpt-6-luna",
        "key_url": "https://platform.openai.com/api-keys",
    },
}
DEFAULT_PROVIDER = "pollinations"

PROMPTS = {
    "fix_grammar": {
        "name": "Fix Grammar",
        "name_fa": "اصلاح گرامر",
        "system_prompt": "You are an expert Persian editor and proofreader. Correct grammar, spelling, punctuation, and نیم‌فاصله according to the Academy of Persian Language and Literature. Preserve the author's tone and meaning. Return only the final corrected text.",
        "prefix": "متن زیر را ویرایش کن: ",
    },
}

logger = logging.getLogger(__name__)


# Seeded once into the user's own (editable) prompt list.
DEFAULT_USER_PROMPTS = [
    {
        "name": "Fix Grammar",
        "name_fa": "اصلاح گرامر",
        "system_prompt": (
            "You are an expert Persian (Farsi) editor and proofreader. Correct the text below according to the "
            "standards of the Academy of Persian Language and Literature.\n\n"
            "Rules:\n"
            "1. Keep the original meaning, tone and all key facts. Do not add, remove or reorder ideas.\n"
            "2. Fix grammar, spelling and typos. Do not change the author's wording or style unless it is wrong.\n"
            "3. Fix punctuation (، ؛ ؟ « ») and spacing around it.\n"
            "4. Use correct Persian letters (ی، ک) and proper half-spaces (نیم\u200cفاصله), "
            'e.g. "می\u200cخواهم", "کتاب\u200cها".\n'
            "5. Keep numbers, names, links, code and technical terms unchanged.\n\n"
            "Output only the corrected text, with no explanations.\n\n"
            "Text:"
        ),
    },
]


def all_prompts(user_prompts=()):
    """The user's prompts ({name, system_prompt}), keyed 'user:<name>'."""
    return {f"user:{p['name']}": {"prefix": "", **p} for p in user_prompts}


def build_request(text, prompt="fix_grammar", provider=DEFAULT_PROVIDER, api_key="", model=""):
    """Return (url, headers, payload) for one chat-completions call; `prompt` is a built-in key or a prompt dict."""
    prov = PROVIDERS.get(provider, PROVIDERS[DEFAULT_PROVIDER])
    if isinstance(prompt, str):
        prompt = PROMPTS[prompt]
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {
        "model": model or prov["model"],
        "messages": [
            {"role": "system", "content": prompt["system_prompt"]},
            {"role": "user", "content": f"{prompt['prefix']}{text}"},
        ],
        "temperature": 0.0,
    }
    return prov["url"], headers, payload


def parse_reply(data):
    """Extract the corrected text from a chat-completions JSON reply; raises KeyError if empty."""
    msg = data["choices"][0]["message"]
    result = (msg.get("content") or msg.get("reasoning") or "").strip()
    m = re.search(r"<corrected\s*text>(.*?)</corrected\s*text>", result, re.DOTALL)
    if m:
        result = m.group(1).strip()
    if not result:
        raise KeyError("content")
    return result


def fix_text(text: str, prompt_key: str = "fix_grammar", provider=DEFAULT_PROVIDER, api_key="", model="") -> str:
    if not text.strip() or prompt_key not in PROMPTS:
        return text
    url, headers, payload = build_request(text, prompt_key, provider, api_key, model)
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=60)
        resp.raise_for_status()
        return parse_reply(resp.json())
    except requests.RequestException as e:
        logger.error("LLM request failed: %s", e)
        raise RuntimeError(f"LLM request failed: {e}") from e
