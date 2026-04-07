# Production Compose

## 文件

- `docker-compose.prod.yml`
- `.env.prod.example`

## 使用方式

```bash
cd /Users/link/work/ai-manga-factory/infra/compose
cp .env.prod.example .env.prod
bash /Users/link/work/ai-manga-factory/scripts/validate_prod_env.sh .env.prod
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
```

如果需要同时启动观测栈：

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod --profile observability up -d --build
```

## 对外入口

- `PUBLIC_HTTP_PORT` 控制统一入口端口
- Web、API、`/health`、`/metrics` 都通过 Caddy 暴露

## 数据与凭证卷

- 默认使用命名卷 `app_data` 和 `app_secrets`，这样在 Lima/Colima 之类的 Docker runtime 上更稳
- 如果你需要强制绑定宿主机目录，可在 `.env.prod` 中设置：
  - `APP_DATA_MOUNT=/absolute/path/to/data`
  - `APP_SECRETS_MOUNT=/absolute/path/to/secrets`

## macOS + Lima

如果你在 macOS 上遇到 Docker Desktop / Colima 拉取镜像慢或不稳定，可以直接使用仓库内置的 Lima 方案：

```bash
cd /Users/link/work/ai-manga-factory
bash scripts/start_lima_tuna_runtime.sh
```

对应配置文件：

- `infra/compose/lima/tuna-docker-rootful.yaml`

## 建议

- 首次启动前先修改 `.env.prod` 里的口令和 bootstrap token
- 生产环境优先替换掉默认的 `POSTGRES_PASSWORD`
- 如果启用对象存储或网盘 API 模式，先准备好 `secrets/` 下的凭证目录
- 也可以直接使用 `bash /Users/link/work/ai-manga-factory/scripts/deploy_prod.sh`
