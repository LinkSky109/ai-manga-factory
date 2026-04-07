# Deployment Drill Record

- Timestamp: 20260406-135301
- Env File: /Users/link/work/ai-manga-factory/infra/compose/.env.prod
- Git SHA: b85178fa80e11072cfe17e7f6a358c090398680f
- Git Branch: main
- Planned Release Manifest: /Users/link/work/ai-manga-factory/backups/releases/release-manifest-20260406-135301.md
- Overall Result: PASS

## Verify Production Stack

- Status: PASS
- Command: `cd '/Users/link/work/ai-manga-factory' && ENV_FILE='/Users/link/work/ai-manga-factory/infra/compose/.env.prod' bash scripts/verify_prod_stack.sh`

```text
[1/3] Validate production env
Production env validation passed: /Users/link/work/ai-manga-factory/infra/compose/.env.prod

[2/3] Validate Docker Compose
Docker Compose config is valid.

[3/3] Validate Caddy config
{"level":"info","ts":1775454781.552138,"msg":"using config from file","file":"/Users/link/work/ai-manga-factory/infra/caddy/Caddyfile"}
{"level":"info","ts":1775454781.552706,"msg":"adapted config to JSON","adapter":"caddyfile"}
{"level":"warn","ts":1775454781.552717,"msg":"Caddyfile input is not formatted; run 'caddy fmt --overwrite' to fix inconsistencies","adapter":"caddyfile","file":"/Users/link/work/ai-manga-factory/infra/caddy/Caddyfile","line":2}
{"level":"info","ts":1775454781.5529559,"logger":"http.auto_https","msg":"automatic HTTPS is completely disabled for server","server_name":"srv0"}
{"level":"info","ts":1775454781.5530639,"logger":"http","msg":"servers shutting down with eternal grace period"}
{"level":"info","ts":1775454781.553252,"logger":"tls.cache.maintenance","msg":"started background certificate maintenance","cache":"0x393ed24ddd00"}
{"level":"info","ts":1775454781.553287,"logger":"tls.cache.maintenance","msg":"stopped background certificate maintenance","cache":"0x393ed24ddd00"}
Valid configuration

Production stack verification completed.

```

## Create Release Manifest

- Status: PASS
- Command: `cd '/Users/link/work/ai-manga-factory' && ENV_FILE='/Users/link/work/ai-manga-factory/infra/compose/.env.prod' bash scripts/create_release_manifest.sh`

```text
Release manifest created: /Users/link/work/ai-manga-factory/backups/releases/release-manifest-20260406-135301.md

```

