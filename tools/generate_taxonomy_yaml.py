import os
import re
import yaml
import time
import json
import httpx
import asyncio
import logging
import argparse
from pathlib import Path
from slugify import slugify
from datetime import datetime
from tenacity import retry, stop_after_attempt, wait_random_exponential

# === Constants ===
CHUNK_CHAR_LIMIT = 4000
VERSION = 3
logging.basicConfig(format='[%(levelname)s] %(message)s', level=logging.INFO)

# === System Prompts ===

SYSTEM_PROMPT_KNOWLEDGE = """You are an expert assistant that creates high-quality InstructLab-compatible knowledge YAML files (qna.yaml).
Use schema version 3 and follow this format:
- version: 3
- domain: "science/radiology" (as an example)
- created_by: GitHub username or author
- document_outline: 1-line description of document
- seed_examples:
  - context: snippet from document
    questions_and_answers:
      - question: detailed and grounded
        answer: well-formed detailed factual answer
Return only valid YAML, no commentary or explanation.
"""

SYSTEM_PROMPT_SKILL = """You are an expert assistant that creates high-quality InstructLab-compatible compositional skill YAML files (qna.yaml).
Use schema version 3 and follow this format:
- version: 3
- task_description: what the skill teaches the model (e.g. "Convert camelCase to snake_case")
- created_by: GitHub username or author
- seed_examples: list of question-answer pairs
If skill is grounded, include context. Return only valid YAML.
"""

# === Prompt Generator ===

def generate_prompt(mode, chunk, args):
    if mode == "knowledge":
        return f"""{SYSTEM_PROMPT_KNOWLEDGE}

Domain: {args.domain}
Created By: {args.created_by}

---
{chunk}
"""
    elif mode == "skill":
        skill_type = "grounded" if args.grounded else "ungrounded"
        return f"""{SYSTEM_PROMPT_SKILL}

Skill Type: {skill_type}
Created By: {args.created_by}
Task: {args.task or 'Unnamed'}

---
{chunk}
"""
    raise ValueError("Invalid mode")

# === File Helpers ===

def read_file(path):
    return Path(path).read_text(encoding="utf-8")

def write_file(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    logging.info(f"✅ Saved: {path}")

def write_attribution(source_path, out_dir):
    content = f"Source: {source_path.name}\nPath: {source_path.resolve()}\nLicense: Unknown"
    write_file(out_dir / "attribution.txt", content)

def chunk_text(text, limit=CHUNK_CHAR_LIMIT):
    parts, current, total = [], [], 0
    for line in text.splitlines():
        line_len = len(line)
        if total + line_len > limit:
            parts.append("\n".join(current))
            current, total = [], 0
        current.append(line)
        total += line_len
    if current:
        parts.append("\n".join(current))
    return parts

# === LLM Handlers ===

@retry(stop=stop_after_attempt(3), wait=wait_random_exponential(min=5, max=20))
async def call_openai(prompt, model):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.3,
            },
            timeout=120,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

@retry(stop=stop_after_attempt(3), wait=wait_random_exponential(min=5, max=20))
async def call_ollama(prompt, model):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:11434/api/chat",
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False
            },
            timeout=120
        )
        response.raise_for_status()
        return response.json()["message"]["content"]

async def call_model(prompt, model, provider):
    if provider == "openai":
        return await call_openai(prompt, model)
    elif provider == "ollama":
        return await call_ollama(prompt, model)
    raise ValueError("Unsupported provider")

# === Processor ===

async def process_file(file_path, args, semaphore):
    async with semaphore:
        try:
            logging.info(f"📄 Processing: {file_path}")
            content = read_file(file_path)
            chunks = chunk_text(content, limit=args.max_tokens * 4)
            for i, chunk in enumerate(chunks):
                prompt = generate_prompt(args.mode, chunk, args)
                output = await call_model(prompt, args.model, args.provider)
                subname = f"{slugify(file_path.stem)}-part-{i+1}"
                out_path = Path(args.output_dir) / args.mode / args.domain / subname / "qna.yaml"
                write_file(out_path, output)
                write_attribution(file_path, out_path.parent)
        except Exception as e:
            logging.error(f"❌ Error processing {file_path.name} chunk {i+1}: {e}")

# === Main CLI ===

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=["ollama", "openai"], default="ollama")
    parser.add_argument("--api-key", help="OpenAI API key (required if using --provider openai)")
    parser.add_argument("--model", required=True)
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", default="taxonomy")
    parser.add_argument("--mode", choices=["knowledge", "skill"], required=True)
    parser.add_argument("--domain", required=True)
    parser.add_argument("--created-by", required=True)
    parser.add_argument("--task", help="Skill task description")
    parser.add_argument("--grounded", action="store_true", help="Use grounded format for skill")
    parser.add_argument("--max-tokens", type=int, default=8000)
    parser.add_argument("--concurrency", type=int, default=2)
    args = parser.parse_args()

    if args.provider == "openai":
        if not args.api_key:
            raise ValueError("❌ You must provide --api-key for OpenAI.")
        os.environ["OPENAI_API_KEY"] = args.api_key

    files = list(Path(args.input_dir).rglob("*.md"))
    if not files:
        logging.warning("⚠️ No markdown files found.")
        return

    sem = asyncio.Semaphore(args.concurrency)
    await asyncio.gather(*(process_file(f, args, sem) for f in files))

if __name__ == "__main__":
    asyncio.run(main())
