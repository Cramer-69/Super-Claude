# AWS Conductor cutover

This is the single supported production path for the first TypingMind proof.
Provider, Mem0, and Firecrawl credentials stay in AWS Systems Manager Parameter
Store. TypingMind receives only the Conductor bearer key.

## 1. Authorize the two account boundaries

The current local `fabric` profile is a placeholder. Configure it once with
the AWS access-portal Start URL and the permitted role for account
`209479275988`, then log in:

```bash
aws configure sso --profile fabric
aws sso login --profile fabric
gh auth login
```

`aws configure sso` asks for the organization's AWS access-portal URL, SSO
region, account, and role. It does not ask for an AI-provider key. The later
bootstrap command is intentionally the only place provider keys are entered.

## 2. Bootstrap AWS and enter credentials privately

From the repository root:

```bash
.venv/bin/python -m scripts.bootstrap_aws --profile fabric
```

The script uses hidden terminal input for these four SecureString parameters:

- `/super-claude/prod/CONDUCTOR_API_KEY`
- `/super-claude/prod/OPENAI_API_KEY`
- `/super-claude/prod/MEM0_API_KEY`
- `/super-claude/prod/FIRECRAWL_API_KEY`

Press Enter to keep an existing parameter. The script also creates or verifies
the ECR repository, restricts the `gha-super-claude` trust policy to
`Cramer-69/Super-Claude` on `main`, and sets the repository variable
`AWS_ROLE_ARN`.

## 3. Build and deploy an immutable image

Merge the cutover branch to `main`. The ECR workflow first runs the Python test
suite and then publishes both the commit SHA and `latest` tags. Deploy the exact
SHA, never `latest`:

```bash
.venv/bin/python -m scripts.deploy_aws \
  --profile fabric \
  --image-tag "$(git rev-parse HEAD)"
```

The stack creates App Runner with one vCPU, two GB memory, exactly one active
instance, SSM secret injection, and monthly alerts at $10, $20, and $25.

## 4. Verify before TypingMind

Replace `HOST` with the script output. Retrieve the Conductor key in your own
terminal or password manager; do not paste it into chat or source files.

```bash
curl -fsS "https://HOST/health/live"
curl -fsS "https://HOST/health/ready"
curl -fsS -H "Authorization: Bearer $CONDUCTOR_API_KEY" \
  "https://HOST/v1/models"
```

Expected results are `live`, `ready`, and a single model named `conductor`.
Unauthenticated `/v1/models`, `/v1/chat/completions`, `/api/chat`,
`/api/web/*`, and the voice credit routes must return `401`.

## 5. TypingMind custom model

- Name: `Ara Conductor — OpenAI Lead`
- Endpoint: `https://HOST/v1/chat/completions`
- Model ID: `conductor`
- Context length: `16000`
- Header: `Authorization: Bearer <CONDUCTOR_API_KEY>`
- Streaming: enabled
- Plugins: disabled for the first proof

Run the memory and web acceptance prompts from separate TypingMind chats. The
web response must contain a visible `Sources` section with clickable links.
