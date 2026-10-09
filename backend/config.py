"""Exact model requirement: no alternate provider or fallback model."""
from pathlib import Path
import os
import json
import re
from contextvars import ContextVar

import httpx

from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

HW_ROOT = Path(__file__).resolve().parents[1]
MODEL_NAME = 'gpt-6-luna'
PORTKEY_URL = 'https://api.portkey.ai/v1'
MODEL_CALL_CONTEXT = ContextVar('campus_model_call_context', default=None)
RESPONSE_HEADER_NAMES = frozenset({'x-request-id', 'request-id', 'x-portkey-trace-id',
    'x-portkey-provider', 'x-portkey-config', 'x-portkey-cache-status',
    'x-portkey-last-used-option-index', 'x-portkey-retry-attempt-count'})


def model_matches(reported):
    return isinstance(reported, str) and re.fullmatch(re.escape(MODEL_NAME) + r'(?:-\d{4}-\d{2}-\d{2})?', reported) is not None


def create_model(record_evidence=None):
    load_dotenv(HW_ROOT / '.env', override=False)
    load_dotenv(HW_ROOT.parent / '.env', override=False)
    api_key = os.environ.get('PORTKEY_API_KEY', '').strip()
    if not api_key:
        raise ValueError('PORTKEY_API_KEY is required in the project .env or environment')
    async def requested(request):
        if request.method != 'POST': return
        body = json.loads(request.content)
        if record_evidence:
            record_evidence('model_http_requested', {'endpoint':str(request.url), 'model':body.get('model'),
                'reasoning_effort':body.get('reasoning_effort'), 'max_completion_tokens':body.get('max_completion_tokens'),
                'tool_names':[tool.get('function', {}).get('name') for tool in body.get('tools', [])],
                'routing_config_header_present':'x-portkey-config' in request.headers})
        if body.get('model') != MODEL_NAME:
            raise RuntimeError('Refusing an outbound request for any model except ' + MODEL_NAME)

    async def responded(response):
        await response.aread()
        try: body = response.json()
        except ValueError: body = {}
        reported = body.get('model')
        evidence = {'http_status':response.status_code, 'requested':MODEL_NAME, 'reported':reported,
            'response_id':body.get('id'), 'usage':body.get('usage'),
            'headers':{key:value for key,value in response.headers.items() if key in RESPONSE_HEADER_NAMES},
            'model_matches':model_matches(reported)}
        if record_evidence: record_evidence('model_http_response', evidence)
        if response.is_success and not model_matches(reported):
            raise RuntimeError(f'Portkey model mismatch: required {MODEL_NAME}, reported {reported!r}; tools will not execute')

    http_client = httpx.AsyncClient(trust_env=False, event_hooks={'request':[requested], 'response':[responded]})
    client = AsyncOpenAI(api_key=api_key, base_url=PORTKEY_URL, http_client=http_client,
                         default_headers={'x-portkey-api-key': api_key},
                         timeout=30, max_retries=0)
    return OpenAIChatModel(MODEL_NAME, provider=OpenAIProvider(openai_client=client),
                           settings={'openai_reasoning_effort':'none'}), client
