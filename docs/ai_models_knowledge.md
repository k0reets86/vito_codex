# AI Models & Providers (VITO)

Updated: 2026-02-24

## OpenAI API
- Requires API key; use `Authorization: Bearer` header. citeturn7search0
- Models and capabilities are listed in the official API docs (chat/completions, embeddings, images). citeturn7search0

## Anthropic API
- Requires API key; uses `x-api-key` header and versioning headers. citeturn7search1
- Claude models are accessed via the Messages API. citeturn7search1

## Google Gemini API
- Access via Google AI API key; uses Generative Language API endpoints. citeturn7search2

## OpenRouter
- Aggregates models from multiple providers; uses a single API key to access many models. citeturn7search3

## Perplexity API
- API access via API key; supports online/grounded answers (per Perplexity docs). citeturn7search4

## Replicate
- Inference API with model registry; access via API token and REST endpoints. citeturn7search5

---

Next: add provider-specific rate limits, pricing, and safety policies per model family.
