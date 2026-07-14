# Ara Conductor Cloudflare Worker

This is the deployed, lightweight outlet for TypingMind and Ara. It provides:

- `GET /health`
- `POST /api/chat`
- `POST /v1/chat/completions` (OpenAI-compatible)
- `GET|POST /api/memories`
- `GET|POST|PATCH /api/tasks`
- A small protected chat page at `/`

## Required secrets

Set these with Wrangler; never commit their values:

```sh
npx wrangler secret put OPENAI_API_KEY
npx wrangler secret put BRIDGE_API_KEY
```

Optional providers can be added later without changing the public contract:

```sh
npx wrangler secret put PERPLEXITY_API_KEY
npx wrangler secret put ANTHROPIC_API_KEY
```

## Initialize persistence

```sh
npx wrangler d1 execute d1-rest-db --remote --file schema.sql
```

## Validate and deploy

```sh
npx wrangler deploy --dry-run
npx wrangler deploy --keep-vars
```

Clients authenticate with `Authorization: Bearer <BRIDGE_API_KEY>`. Use
`X-User-Id` to keep memories and tasks separated by user.
