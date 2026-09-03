# Volcengine file-ASR modes

Verified against the official Volcengine documentation in August 2026.

| Mode | Resource ID | Endpoint(s) | Flow | Local Base64 |
|---|---|---|---|---|
| `standard-v1` | `volc.bigasr.auc` | `/api/v3/auc/bigmodel/submit`, `/query` | asynchronous | no |
| `standard-v2` | `volc.seedasr.auc` | `/api/v3/auc/bigmodel/submit`, `/query` | asynchronous | no |
| `idle-v1` | `volc.bigasr.auc_idle` | `/api/v3/auc/bigmodel/idle/submit`, `/idle/query` | asynchronous, up to 24h | no |
| `turbo-v1` | `volc.bigasr.auc_turbo` | `/api/v3/auc/bigmodel/recognize/flash` | synchronous | yes |

Do not derive `volc.seedasr.auc_idle` or `volc.seedasr.auc_turbo`: these resource IDs are not documented.

## Authentication

All v3 modes use:

- `X-Api-App-Key`: speech application APP ID
- `X-Api-Access-Key`: speech application Access Token
- `X-Api-Resource-Id`: exact value from the table
- `X-Api-Request-Id`: client-generated UUID
- `X-Api-Sequence: -1`: submit/Turbo request

The console's speech Secret Key is not used by these requests.

## Terminal status

- `20000000`: success
- `20000001`: processing
- `20000002`: queued
- other values: terminal error; retain the status, message, and `X-Tt-Logid`

## Limits

- Standard/idle: URL input, media shorter than 5 hours and smaller than 512 MiB.
- Turbo: URL or Base64 input, no more than 2 hours or 100 MiB. The official page recommends keeping binary uploads near or below 20 MiB when possible.
- Result retention is finite; persist JSON immediately after success.

## Official references

- Standard model API: <https://www.volcengine.com/docs/6561/1354868?lang=zh>
- Product capabilities and limits: <https://www.volcengine.com/docs/6561/1354871?lang=zh>
- Turbo API: <https://www.volcengine.com/docs/6561/1631584?lang=zh>
- Idle API: <https://www.volcengine.com/docs/6561/1840838?lang=zh>
- 1.0/2.0 resource mapping: <https://www.volcengine.com/docs/85637/2477587?lang=zh>
- TOS Python SDK: <https://github.com/volcengine/ve-tos-python-sdk>

