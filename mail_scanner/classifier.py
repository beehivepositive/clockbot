"""AI-powered mail classification using Ollama (free) or Claude (paid)."""
import base64
import re
import cv2
import config


def _encode_frame(frame):
    """Encode an OpenCV frame to base64 PNG."""
    _, buffer = cv2.imencode(".png", frame)
    return base64.b64encode(buffer).decode("utf-8")


def _parse_response(text):
    """Parse the structured AI response into a dict."""
    result = {
        "type": "unknown",
        "priority": "unknown",
        "summary": "",
        "sender": "unknown",
        "due_date": "none",
        "raw_response": text,
    }
    patterns = {
        "type": r"TYPE:\s*(.+)",
        "priority": r"PRIORITY:\s*(.+)",
        "summary": r"SUMMARY:\s*(.+)",
        "sender": r"SENDER:\s*(.+)",
        "due_date": r"DUE_DATE:\s*(.+)",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            result[key] = match.group(1).strip()
    return result


def classify_ollama(frame):
    """Classify mail using a local Ollama vision model (free)."""
    import ollama

    b64 = _encode_frame(frame)
    response = ollama.chat(
        model=config.OLLAMA_MODEL,
        messages=[{
            "role": "user",
            "content": config.CLASSIFY_PROMPT,
            "images": [b64],
        }],
    )
    return _parse_response(response["message"]["content"])


def classify_claude(frame):
    """Classify mail using the Claude API (paid)."""
    import anthropic

    b64 = _encode_frame(frame)
    client = anthropic.Anthropic()
    response = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=300,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": b64,
                    },
                },
                {
                    "type": "text",
                    "text": config.CLASSIFY_PROMPT,
                },
            ],
        }],
    )
    return _parse_response(response.content[0].text)


def classify(frame):
    """Classify a mail image using the configured backend."""
    if config.AI_BACKEND == "claude":
        return classify_claude(frame)
    return classify_ollama(frame)
