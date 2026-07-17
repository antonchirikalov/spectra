# SPEC: Переход spectra на opencode serve + HTTP API

Версия: 0.2 (draft)
Дата: 2026-07-17
Статус: предложение, не реализовано
Целевая версия opencode: ≥ 1.18.3 (проверено на локальной установке)
Изменения в 0.2: добавлен раздел 7 «Флоу пайплайнов» (полные флоу Extract / Discovery / Solution Design / standalone, матрица hand-off, параллелизм, failure-семантика); зафиксировано решение о scope миграции (§6).

---

## 1. Цель и контекст

spectra сегодня вызывает агентов opencode через `subprocess.run(["opencode", "run", ...])` — один OS-процесс на каждый шаг агента. Предлагается заменить этот механизм на программный: один долгоживущий сервер `opencode serve` на весь прогон пайплайна, а раннер общается с ним по HTTP (REST + SSE).

Меняется **только транспортный слой** (`run_agent()` / `run_agent_write()` в раннерах). Агенты, промпты, пайплайны, state.json-ledger, MCP-серверы, модельный роутинг — без изменений.

### 1.1. Что это даёт

| Проблема сейчас | Как решается serve + API |
|---|---|
| Холодный старт процесса на каждый шаг (~15 стартов за прогон Extract) | Сервер стартует один раз; сессии дешёвые |
| Хак `_opencode_env()`: temp-директории APPDATA/XDG, чтобы параллельные процессы не дрались за SQLite | Сессии изолированы на стороне сервера; хак удаляется |
| Heartbeat вслепую: «прошло N секунд» | SSE-стрим: виден каждый tool call агента в реальном времени |
| Ошибки провайдера ловятся regex по тексту stdout (`_detect_api_error`) | Типизированные события ошибок в SSE |
| Отмена по таймауту = убийство дерева процессов (хрупко на Windows) | `POST /session/:id/abort` — чистая отмена |
| Отладка зависшего агента — post-mortem по `agent.events.jsonl` | `opencode attach <url>` — подключить TUI к живому серверу |
| Permissions пропускаются флагом `--dangerously-skip-permissions` | Программные approvals через `POST /session/:id/permissions/:permissionID` |

### 1.2. Что НЕ меняется

- Определения агентов в `.opencode/agents/*.md`
- Провайдеры и модели в `opencode.json`, роутинг через `plan/params.yaml`
- MCP-серверы (pdf-reader, tavily-remote, mcp-atlassian, docx-mcp)
- Промпт-файлы (`prompts/*.md`), контракт «Read your task from: `<path>`»
- Hand-off через файлы (`extract.json`, verdicts, `_requirements.md`, …)
- `state.json` ledger: статусы шагов, `resume`, `--retry-failed`, `--force-step`
- Логика фаз, critic-циклы, safety caps

---

## 2. Текущая архитектура (subprocess)

```
requirements_runner.py
  │
  ├─ Phase 0: сканирование входа → manifest.json          (чистый Python)
  │
  ├─ Phase 1: ThreadPoolExecutor(workers=3)
  │     └─ на каждый источник:
  │           subprocess: opencode run --agent source_processor
  │                         --model kimi/kimi-k3
  │                         --format json
  │                         --dangerously-skip-permissions
  │                         "Read your task from: prompts/<slug>.md"
  │           ├─ env: изолированные APPDATA/LOCALAPPDATA/XDG (temp dir)
  │           ├─ heartbeat-поток: print каждые 10 с
  │           ├─ timeout AGENT_TIMEOUT_S → kill процесса
  │           ├─ stdout → extract_assistant_text() → parse_json_from_text()
  │           └─ раннер сохраняет extracts/<slug>/extract.json
  │
  ├─ Phase 2: subprocess: opencode run --agent requirements_writer
  │     └─ агент сам пишет _requirements.md через write-tool
  │
  └─ Phase 3: critic ↔ writer цикл (≤ 5 раундов)
        └─ subprocess на каждый verdict/revision
```

Характеристики:

- **Стоимость вызова**: каждый шаг = boot opencode (Bun + Go TUI-процессы), загрузка `opencode.json`, подъём MCP-серверов, потом собственно работа агента, потом выход.
- **Наблюдаемость**: раннер ничего не знает о внутреннем состоянии агента до завершения процесса; heartbeat — просто часы.
- **Детекция ошибок**: `_detect_api_error(stdout)` ищет подстроки вида `database is locked`, 401/429 в тексте JSON-стрима.
- **Два режима вызова**:
  - `run_agent()` — агент возвращает результат в stdout как JSON-блок (source_processor, arch_probe);
  - `run_agent_write()` — агент пишет артефакт на диск write-инструментом (writer, critic, arch_critic, designer, selector, design critic); раннер проверяет файл после выхода.

---

## 3. Целевая архитектура (serve + API)

### 3.1. Модель

opencode — клиент-серверное приложение: TUI (`opencode`), Web (`opencode web`), IDE-плагины — все они клиенты одного HTTP-сервера. `opencode serve` поднимает сервер без UI и публикует OpenAPI 3.1 спецификацию на `GET /doc`. Раннер становится ещё одним клиентом этого сервера.

```
requirements_runner.py
  │
  ├─ startup: subprocess.Popen(["opencode", "serve", "--port", "0"])
  │     └─ ожидание GET /global/health → { healthy: true, version }
  │
  ├─ на каждый шаг агента:
  │     POST /session                      { title: "<slug>" }         → session id
  │     POST /session/:id/message          { agent, model, parts }     → блокирующий ответ
  │     (параллельно) GET /event (SSE)     → tool calls, статусы, ошибки, permissions
  │     при таймауте: POST /session/:id/abort
  │
  └─ shutdown: POST /instance/dispose (или terminate процесса сервера)
```

Сервер запускается с `cwd = REPO_ROOT` — тогда `.opencode/agents/`, `opencode.json` и MCP-конфиги резолвятся так же, как сейчас.

### 3.2. Используемые эндпоинты

> **Проверено spike'ом 2026-07-17** (`scripts/spike_serve_api.py`, opencode 1.18.3): все эндпоинты ниже работают; точные шейпы — в §3.9. OpenAPI-спека сохранена в `docs/openapi/opencode-1.18.3.json`, захваченные события — в `docs/openapi/spike_events.jsonl`.

| Эндпоинт | Назначение в раннере |
|---|---|
| `GET /global/health` | Ожидание готовности сервера при старте |
| `GET /agent` | Sanity-check: нужные агенты зарегистрированы (после старта сервера) |
| `GET /mcp` | Sanity-check: MCP-серверы поднялись |
| `POST /session` | Создать сессию на шаг; body: `{ title?, parentID? }` |
| `POST /session/:id/message` | Отправить промпт и **дождаться ответа**; body: `{ agent, model, parts: [{type:"text", text}] }` |
| `POST /session/:id/prompt_async` | Тот же промпт без ожидания (204) — вариант для fan-out Phase 1 |
| `GET /session/:id/message` | Дочитать сообщения/parts сессии (для async-варианта) |
| `GET /session/status` | Статусы всех сессий (busy/idle) — мониторинг пула |
| `POST /session/:id/abort` | Отмена по таймауту |
| `POST /session/:id/permissions/:permissionID` | Ответ на запрос разрешения (HITL); body: `{ response, remember? }` |
| `GET /event` | SSE-стрим событий сервера (первое событие — `server.connected`) |
| `GET /session/:id/children` | Дочерние сессии (если агент сам спавнит сабагентов) |
| `POST /instance/dispose` | Корректная остановка сервера |
| `GET /doc` | OpenAPI-спека — источник истины по типам при реализации |

Точные имена полей и типов событий SSE проверены spike'ом — см. §3.9. Источник истины на будущее — OpenAPI-спека `/doc` целевой версии opencode.

### 3.9. Проверенные шейпы API (spike 2026-07-17, opencode 1.18.3)

**Health:** `GET /global/health` → `{"healthy": true, "version": "1.18.3"}`.

**Агенты:** `GET /agent` → 19 агентов: все 12 агентов spectra + 7 встроенных (build, plan, general, explore, compaction, title, summary). Имя агента = имя `.md`-файла.

**MCP:** `GET /mcp` → `{"<name>": {"status": "connected"|"failed", "error"?}}`. На spike: pdf-reader, tavily-remote, mcp-atlassian-scnsoft, docx-mcp, ss-gateway, huggingface — connected; github — failed (предсуществующая проблема OAuth, пайплайнам не нужен).

**Создание сессии:** `POST /session` body `{"title": "..."}` → `{id, projectID, directory, path, slug, time, title, tokens, cost, version}`.

**Отправка промпта (рабочий шейп):**
```json
POST /session/:id/message
{
  "agent": "source_processor",
  "model": {"providerID": "kimi", "modelID": "kimi-k3"},
  "parts": [{"type": "text", "text": "Read your task from: <path>"}]
}
```
Маппинг `provider/model` → `{providerID, modelID}`: split по первому `/`. Ответ `200 OK`:
```json
{
  "info": {"id", "sessionID", "role", "agent", "mode", "modelID", "providerID", "parentID", "path", "time", "tokens", "cost", "finish"},
  "parts": [{"type": "step-start"}, {"type": "reasoning"}, {"type": "text", "text": "..."}, {"type": "step-finish"}]
}
```
Финальный текст агента = конкатенация `parts[type=text].text`. В `info` — `tokens` и `cost` (можно писать в ledger для учёта стоимости прогона — бонус против subprocess).

**SSE-стрим:** `GET /event` → строки `data: {json}`. Конверт события: `{"id": "evt_...", "type": "<type>", "properties": {...}}`; фильтр по сессии — `properties.sessionID`. Наблюденные типы (spike): `server.connected`, `server.heartbeat`, `session.created`, `session.updated`, `session.status` (`{status: {type: "busy"|"idle"}}`), `session.idle`, `session.error` (`{error: {name, data: {message}}}`), `session.diff`, `message.updated`, `message.part.updated`, `message.part.delta`, `catalog.updated`, `integration.updated`, `plugin.added`, `reference.updated`. В спеке дополнительно: `EventPermissionAsked` / `EventPermissionReplied` (+V2), семейство `SessionNext*` (ToolCalled/ToolSuccess/ToolFailed, Text*, Reasoning*, Compaction*).

**Маппинг событий → `error_kind` (закрывает открытый вопрос плана):**

| Событие / условие | error_kind | Действие раннера |
|---|---|---|
| client-side таймер истёк | `timeout` | `POST /session/:id/abort` → ждать `session.error {name: "MessageAbortedError"}` → fail шага |
| `session.error` с `error.name` ≠ MessageAbortedError | `api` | текст из `error.data.message` → fail без regex |
| HTTP ≠ 200 на `/message` | `process` | body ответа → fail |
| HTTP 200, но в финальном тексте нет JSON-блока | `no_json` | как сейчас (parse_json_from_text) |
| `session.idle` после `/message` | — | нормальное завершение шага |

**Отмена:** `POST /session/:id/abort` → `200 true`; `GET /session/status` после — пусто (`{}`, нет busy-сессий); на сессию прилетает `session.error {name: "MessageAbortedError"}` — использовать как подтверждение отмены.

**Async-вариант:** `POST /session/:id/prompt_async` → `204` (проверен на abort-тесте); результат дочитывается через `GET /session/:id/message` и SSE.

**parentID:** `POST /session` принимает `parentID` — сессии прогона можно группировать под одной корневой («run-<run_id>») для удобной навигации в `opencode attach` и `GET /session/:id/children`. Рекомендация: использовать.

### 3.3. Тонкий клиент: новый модуль `opencode_client.py` — РЕАЛИЗОВАНО (этап 1, 2026-07-17)

Модуль `opencode_client.py` в корне репо (~250 строк, `httpx`). Тесты: `tests/test_opencode_client.py` (11 шт., MockTransport, без живого сервера). Два урока из реализации:

1. **Windows tree-kill.** `proc.terminate()` убивает только `.cmd`-обёртку — реальный бинарник сервера (внук) остаётся жить. `stop()` делает `POST /instance/dispose`, затем `taskkill /PID <pid> /T /F` на Windows.
2. **Гонка ленивой инициализации.** Потоки Phase 1 одновременно вызывают старт сервера — нужен double-checked locking (`_SERVER_LOCK`), иначе стартуют два сервера (поймано на golden-run).

Публичный интерфейс (скетч):

```python
class OpencodeServer:
    def start(self) -> None: ...            # Popen serve, дождаться /global/health
    def stop(self) -> None: ...             # /instance/dispose → terminate

    def list_agents(self) -> list[str]: ...
    def mcp_status(self) -> dict: ...

    def run_step(
        self,
        agent: str,                 # "source_processor"
        model: str,                 # "kimi/kimi-k3" → {providerID, modelID}
        prompt: str,                # "Read your task from: <path>"
        slug: str,                  # для логов и title сессии
        timeout_s: int,
        on_event: Callable[[dict], None] | None = None,
        permission_handler: Callable[[dict], str] | None = None,
    ) -> StepResult: ...
        # StepResult: success, final_text, error_kind (timeout/api/process/no_json),
        # session_id, event_log (сохраняется в agent.events.jsonl как сейчас)
```

Внутри `run_step`:

1. `POST /session` → session id.
2. Подписка на `GET /event` (фоновый поток), фильтр по session id.
3. `POST /session/:id/message` — блокирующий вызов с client-side timeout.
4. Во время ожидания: события SSE → heartbeat с содержанием (`tool: read_pdf`, `tool: tavily_search`, …) вместо слепых секунд; события ошибок → классификация `error_kind`; permission-запросы → `permission_handler` (по умолчанию — авто-approve, эквивалент `--dangerously-skip-permissions`).
5. Таймаут → `POST /session/:id/abort` → `StepResult(error_kind="timeout")`.
6. Ответ сервера → собрать текст финального assistant-сообщения из parts → вернуть.

### 3.4. Параллелизм Phase 1

Текущий `ThreadPoolExecutor(max_workers=N)` сохраняется — но каждый поток теперь держит HTTP-вызов, а не процесс. Альтернатива на будущее: `prompt_async` + единый цикл ожидания по SSE/`/session/status`. В рамках этой миграции остаёмся на потоках — минимальный diff.

Ограничение параллелизма сервером не требуется: семафор остаётся на стороне раннера (`--workers`).

### 3.5. Таймауты и retries

- `AGENT_TIMEOUT_S` сохраняется как есть; реализация — client-side timeout + `abort`.
- Retry-семантика `run_agent()` (`max_retries`, пауза 2 с) сохраняется; каждая попытка — **новая сессия** (чистый контекст, как сейчас новый процесс).
- Ошибки классифицируются по типизированным событиям/HTTP-кодам, а не regex; `_detect_api_error()` удаляется.

### 3.6. Совместимость с ledger (`state.json`)

- Статусы шагов и все команды (`status`, `resume`, `--retry-failed`, `--force-step`) работают без изменений — ledger оперирует шагами, а не процессами.
- Добавляется одно поле: `state.json → step → session_id` — для post-mortem навигации (`opencode attach` + выбор сессии) и отладки.
- При `resume` создаются новые сессии; старые сессии не переиспользуются (поведение идентично сегодняшнему).

### 3.7. Режимы вызова агентов (сохраняются)

| Режим | Агенты | Реализация поверх `run_step` |
|---|---|---|
| JSON из ответа | source_processor, arch_probe | `final_text` → `parse_json_from_text()` (функция остаётся) |
| Файл на диске | writer, critic, arch_critic, designer, selector, design critic | после `StepResult.success` раннер проверяет output-файл (логика остаётся) |

### 3.8. Отладка живого прогона (новая возможность)

Сервер доступен на `127.0.0.1:<port>` всё время прогона. В любой момент:

```powershell
opencode attach http://127.0.0.1:<port>
```

— открывается TUI со всеми сессиями текущего прогона: видно, какой tool call выполняет зависший агент, можно дочитать его контекст. Это заменяет post-mortem разбор `agent.events.jsonl` (файл продолжает писаться для архива).

---

## 4. Маппинг изменений в коде

| Файл | Изменение |
|---|---|
| `opencode_client.py` | **Новый модуль** (~200–300 строк): сервер + `run_step` |
| `requirements_runner.py` | `run_agent()`, `run_agent_write()` → вызовы `OpencodeServer.run_step()`; удаляются `_opencode_env()`, `_run_with_heartbeat()`, `_detect_api_error()`, `OPENCODE_EXE`-резолв; lifecycle сервера в `main()` |
| `solution_design_runner.py` | Аналогично (те же функции вызова) |
| `state.json` | + опциональное поле `session_id` на шаг |
| `.venv` / `requirements.txt` | + `httpx` (проверить наличие; уже нужен confluence-publisher) |
| `README.md` / `README_RU.md` | Обновить разделы про архитектуру и отладку |

Удаляемый хак, который стоит отметить явно: изоляция SQLite через temp `APPDATA`/`XDG_*` (`_opencode_env`) больше не нужна — сессии изолированы на сервере, параллельность нативная.

## 5. Риски и ограничения

| Риск | Митигация |
|---|---|
| Известный баг: сессии через REST могут виснуть, когда агент спавнит сабагента через Task tool (issue #6573) | Агенты spectra сабагентов не спавнят (плоская структура); добавить в sanity-check отсутствие Task-permissions у наших агентов; следить за issue |
| Изменения API между версиями opencode | Зафиксировать поддерживаемую версию; sanity-check `GET /global/health → version` при старте; типы брать из `/doc` |
| SSE на Windows/прокси — буферизация | `httpx` stream с явным read-timeout; heartbeat по последнему событию, а не по wall clock |
| Зависший сервер блокирует весь пайплайн | Watchdog в раннере: `GET /global/health` по таймеру; при смерти сервера — restart + шаги `running → pending` (уже есть в ledger) |
| Нет официального Python SDK | Тонкий клиент + OpenAPI-спека; площадь контакта ~10 эндпоинтов |

## 6. План внедрения

Утверждённый план переноса: **`docs/MIGRATION_PLAN_SERVE_API.md`** (v1.0 от 2026-07-17, 3.5–5 дней).

Решение о рамках (2026-07-17): **effort_estimator и word_form_builder вне scope миграции** — они standalone-агенты ручного вызова и транспортом раннеров не пользуются; их определения не меняются. По той же причине не затрагиваются illustrator и confluence_publisher.

Этапы (детали — в плане):
0. Разведка API (spike, точные шейпы из `/doc`).
1. Модуль `opencode_client.py`.
2. `requirements_runner.py` (Extract + Discovery) за флагом `--transport`.
3. `solution_design_runner.py`.
4. Зачистка и релиз (`serve` становится default).

Опционально позже: permissions через API вместо skip-флага; async fan-out вместо потоков; watchdog-перезапуск сервера.

---

## 7. Флоу пайплайнов

Полное описание всех пайплайнов spectra: какие агенты где участвуют, что передают друг другу, где параллелизм, какие лимиты и ветвления. Детали сверены с кодом `requirements_runner.py` и `solution_design_runner.py`.

### 7.0. Общие принципы взаимодействия

- **Контракт вызова единый:** раннер рендерит task-файл в `prompts/<slug>.md` → агент получает сообщение `Read your task from: <path>` → читает task-файл первым делом.
- **Все hand-off — файлы на диске.** Агенты никогда не общаются напрямую; только через артефакты (extract.json, verdict.md, _requirements.md, …). Это и есть основа crash recovery.
- **Два режима ответа агента:**
  - JSON в stdout (парсит раннер): source_processor, arch_probe;
  - артефакт на диске через write-инструмент: все остальные.
- **Ledger:** каждый шаг пишется в `state.json` с gate-проверкой артефакта (существует + ≥ 200 байт + формат: у verdict — первая строка `VERDICT:`, у requirements — `# Requirements:` и `| FR-`). Шаг со статусом `running` при старте → `pending` (auto-recovery).
- **Модельный роутинг:** `plan/params.yaml` → per-agent override; дефолт `kimi/kimi-k3`; `--model` CLI инжектится всем агентам без явного override.
- **Лимиты:** `AGENT_TIMEOUT_S = 3600` на любой вызов агента; JSON-агенты — `max_retries = 1` (2 попытки); heartbeat каждые 10 с.
- **Модельные ID шагов:** `extract:<slug>`, `phase2:requirements_writer`, `critic:r<N>`, `revision:r<N>` (requirements); `designer-<model-slug>`, `selector`, `critic:r<N>`, `revision:r<N>` (solution design). Используются в `--force-step`.

### 7.1. Extract-пайплайн (`requirements_runner.py run <dir> --mode extract`)

```
Phase 0 (Python)         Phase 1 (параллельно)              Phase 2                  Phase 3 (цикл ≤ 5)
scan → manifest.json     N × source_processor               requirements_writer      critic ──APPROVED──► готово
  файл верх. уровня = 1    (по одному инстансу на файл      _requirements.md  ──►       │
  подпапка = 1 источник    или на подпапку целиком)                                REVISE ▼
                           workers = min(3, N)                                     writer revision ─┐
                         + HITL clarify (≤ 2 раунда)                                    ◄───────────┘
```

**Phase 0 — сканирование (чистый Python, без агентов).** Обход входной папки, классификация по расширению, исключение `plan/`, `.git/`, `__pycache__/`, `outputs/`. Каждой записи `manifest.json` присваивается: `slug`, `kind` (`file` | `subfolder`), `read_tool` (`read` | `mcp_pdf-reader` | `vision`), `assets` (картинки внутри документов).

**Гранулярность источника — что становится одной записью манифеста (и одним инстансом экстрактора в Phase 1):**
- **каждый файл верхнего уровня** входной папки → отдельная запись, свой инстанс `source_processor`;
- **каждая подпапка** → ОДНА запись, один инстанс `source_processor`, который обрабатывает **все файлы подпапки как единый логический источник** (запись манифеста содержит список `files[]`; агент читает их все и пишет один общий `extract.json`). Это сделано для наборов связанных документов (например, RFP + приложения + переписка по нему), где требования надо извлекать сквозные, а не по файлам. Контроль полноты: раннер сверяет `files_processed` из ответа агента со списком `files[]` манифеста и печатает warning, если агент обработал не все файлы подпапки.

**Phase 1 — параллельное извлечение.** Один `source_processor` **на запись манифеста** — то есть на файл верхнего уровня или на подпапку целиком (см. выше); пул `ThreadPoolExecutor`, дефолт `workers = min(3, N)` (CLI `--workers`). Каждый агент: определяет тип документа → грузит стратегию `prompts/source_processor/strategies/<type>.md` → читает источник → возвращает JSON. Раннер парсит stdout и сохраняет `extracts/<slug>/extract.json` + `raw.txt` + `agent.events.jsonl`. Падение одного источника не блокирует остальных.
**HITL:clarify (≤ 2 раунда):** агенты с `needs_clarification: true` → при `--interactive` раннер ставит пайплайн на паузу и спрашивает в терминале; ответ добавляется в промпт, агент перезапускается (`<slug>_retry<N>.md`). Без `--interactive` — пропускается с логом.

**Phase 2 — синтез.** Один `requirements_writer` получает список всех успешных `extract.json` (Tavily-обогащение неизвестных интеграций) → пишет `_requirements.md`. Gate: файл ≥ 200 байт + `# Requirements:` + хотя бы один `| FR-`. Печатается счётчик FR/NFR/BR.

**Phase 3 — critic-цикл (≤ 5 раундов, `MAX_CRITIC_ROUNDS = 5`).** Раунд: `requirements_critic` пишет `verdict.md` → `APPROVED` — стоп, успех. `REVISE` — verdict инжектируется в revision-промпт → `requirements_writer` переписывает `_requirements.md` → следующий раунд. Достижение cap — warning (`REVISE_CAP`), не failure. Падение критика — non-fatal (пайплайн продолжается). Ledger запоминает раунд: `resume` продолжает с `start_round`.

### 7.2. Discovery-пайплайн (`--mode discovery`)

```
Phase 0 → Phase 1 (идентичны Extract, включая HITL) → Phase D1 → Phase D2
                                                        arch_probe   arch_critic
                                                        20–30 вопр.  8–15 вопр.
                                                        (JSON)       discovery_report.md
```

**Phase D1.** Один `arch_probe`: читает все extract.json, оценивает AI-generation признаки источников, делает 3–5 Tavily-поисков → JSON с 20–30 сырыми вопросами в stdout (парсит раннер, сохраняет в `extracts/_arch_probe/`).

**Phase D2.** Один `arch_critic`: читает JSON probe → rejection-фильтр + переписывание пограничных → 8–15 финальных вопросов → пишет `discovery_report.md` (write-инструментом, язык исходных документов).

Особенности: нет critic-цикла, нет ревизий — D2 финализирует пайплайн за один проход. Phase 0/1 полностью общие с Extract: один и тот же прогон может сначала сделать extract, потом discovery на тех же экстрактах (ledger пропустит выполненные шаги).

### 7.3. Solution Design пайплайн (`solution_design_runner.py run <_requirements.md>`)

```
Phase 1 (параллельно, ВСЕ модели)      Phase 2              Phase 3 (цикл ≤ 3)                Phase 4
N × solution_designer                  selector             critic ──APPROVED──►              summary
 (по одному на модель из --models) ──► _solution_design.md ──►    │ REVISE                     (exit 0
                                                               designer(победившая модель)    только при
                                                               revision → overwrite ─┐        APPROVED)
                                                                  ◄──────────────────┘
```

**Phase 1 — параллельная генерация.** Один `solution_designer` на каждую модель из `--models` (дефолт: только `kimi/kimi-k3`). Пул **без ограничения**: `max_workers = len(tasks)` — все модели работают одновременно. Каждый пишет `_design_<model_slug>.md`. Падение модели не блокирует остальных; 0 успешных → abort (exit 1).

**Phase 2 — выбор.** 1 кандидат → копирование + report «Only one candidate». N ≥ 2 → `solution_design_selector`: дисквалификаторы (HIGH) → сравнение по осям → победитель копируется **verbatim** в `_solution_design.md` + `_selection_report.md` (первая строка `WINNING_MODEL:`). Падение selector → fallback: первый успешный кандидант. Раннер парсит `WINNING_MODEL` из репорта → запоминает в ledger.

**Число моделей — как задать (`--models`, `nargs="+"`, дефолт `[kimi/kimi-k3]`):**

```bash
# Одна модель (дефолт) — selector НЕ вызывается вовсе, дизайн копируется
solution_design_runner.py run _requirements.md
# Одна конкретная модель — то же самое
solution_design_runner.py run _requirements.md --models openai/gpt-4o
# Соревнование N моделей — selector выбирает лучшее
solution_design_runner.py run _requirements.md --models kimi/kimi-k3 openai/gpt-4o
```

Особенности: selector и critic всегда на `DEFAULT_MODEL` (kimi/kimi-k3), независимо от `--models`; ревизии Phase 3 делает победившая модель; если из нескольких моделей выжила одна — selector пропускается, выжившая копируется автоматически.

**Phase 3 — critic-цикл (≤ 3 раундов, `MAX_CRITIC_ROUNDS = 3`).** Раунд: `solution_design_critic` → `_verdict_round<N>.md`. `APPROVED` → break. `REVISE` → `solution_designer` **победившей модели** пишет `_design_revised_r<N>.md` (вердикт в промпте) → копируется поверх `_solution_design.md`. Падение критика = трактуется как REVISE. Падение ревизии = текущий дизайн сохраняется. Исчерпание раундов → стоп с последним вердиктом.

**Phase 4 — summary.** Пути артефактов, winning model, финальный вердикт, счётчик `<!-- ILLUSTRATION: -->` плейсхолдеров. **Exit code: 0 только при APPROVED** — можно использовать в CI.

### 7.4. Standalone-агенты (ручной вызов через opencode CLI/TUI, вне раннеров)

```
_requirements.md ──┬─► word_form_builder ──► form_spec.json ──► build_word_form.py ──► form.docx
                   │
_solution_design.md ─┬─► illustrator ──► (фоновый bash × N) PaperBanana ──► illustrations/*.png + _manifest.md
                     ├─► effort_estimator ──► _effort_estimate.md (WBS, часы)
                     └─► (после illustrator/estimator) confluence_publisher ──► publish_to_confluence.py ──► Confluence page
```

- **word_form_builder** — вход: `_requirements.md` + `extracts/`; Tavily-обогащение опций; генерация `.docx` скриптом (bash).
- **illustrator** — вход: документ с `<!-- ILLUSTRATION: -->`; **все иллюстрации параллельно** через фоновый bash (3–5 мин каждая); встраивание PNG в документ с подписями Fig. N.
- **effort_estimator** — вход: `_solution_design.md`; детерминированная арифметика по рубрике; выход только в часах.
- **confluence_publisher** — вход: финальный md (+ папка иллюстраций, + PDF); upsert страницы скриптом; отчёт с URL/версией.

Типовая цепочка поставки: `Extract → Solution Design → illustrator → effort_estimator → confluence_publisher` (плюс `word_form_builder` в ветке уточнений с клиентом).

### 7.5. Матрица hand-off: кто кому что передаёт

| Продюсер | Артефакт | Потребители |
|---|---|---|
| source_processor ×N | `extracts/<slug>/extract.json` | requirements_writer, requirements_critic, arch_probe, word_form_builder |
| requirements_writer | `_requirements.md` | requirements_critic, solution_designer, word_form_builder |
| requirements_critic | `verdict.md` (r<N>) | requirements_writer (revision) |
| arch_probe | probe JSON (`extracts/_arch_probe/`) | arch_critic |
| arch_critic | `discovery_report.md` | человек (воркшоп); опционально word_form_builder |
| solution_designer ×N | `_design_<model>.md` | solution_design_selector |
| solution_design_selector | `_solution_design.md`, `_selection_report.md` | solution_design_critic, illustrator, effort_estimator, confluence_publisher |
| solution_design_critic | `_verdict_round<N>.md` | solution_designer (revision, победившая модель) |
| illustrator | `illustrations/*.png`, `_manifest.md` | confluence_publisher |
| effort_estimator | `_effort_estimate.md` | confluence_publisher, человек |
| word_form_builder | `form.docx` | клиент (заполнение) |

### 7.6. Параллелизм — сводка

| Точка | Механизм | Предел | Комментарий |
|---|---|---|---|
| Extract/Discovery Phase 1 | ThreadPoolExecutor | `--workers`, дефолт min(3, N) | основной fan-out |
| HITL retry-раунд | ThreadPoolExecutor | тот же `--workers` | только flagged slug'и |
| SD Phase 1 | ThreadPoolExecutor | `len(models)` — без cap | все модели одновременно |
| Critic-циклы (оба пайплайна) | последовательно | — | verdict → revision → verdict |
| illustrator | фоновый bash | все плейсхолдеры сразу | внутри одного агента |

### 7.7. Ветвления и failure-семантика

| Событие | Поведение |
|---|---|
| source_processor упал | источник помечается failed, остальные продолжаются; Phase 2 идёт по успешным |
| needs_clarification + нет --interactive | пропуск с логом (вопрос попадёт в `open_questions` экстракта) |
| requirements_writer не написал файл / файл < 200 байт | Phase 2 failed → прогон failed (resume переиграет) |
| requirements_critic упал | non-fatal, warning, цикл завершается |
| critic cap (5 / 3 раунда) | warning, артефакт остаётся последней ревизии; Extract — success, SD — exit 1 |
| одна модель designer упала | остальные продолжаются |
| все designer'ы упали | abort, exit 1 |
| selector упал | fallback — первый успешный кандидант |
| SD revision упала | текущий `_solution_design.md` сохраняется |
| kill раннера в любой точке | `resume` продолжает: `running → pending`, выполненные шаги пропускаются по ledger+gate |

---

## 8. Каталог агентов

Все агенты определены в `.opencode/agents/*.md` с `mode: all`. Вызов всегда единообразный: раннер рендерит task-файл в `prompts/<slug>.md`, агент получает сообщение `Read your task from: <path>`. Модель по умолчанию — `kimi/kimi-k3`; роутинг по агентам — `plan/params.yaml` (`models: { <agent>: provider/model }`).

### 7.1. Пайплайн Extract / Discovery

#### `source_processor` — извлечение требований из одного источника

- **Фаза:** Extract/Discovery Phase 1 (параллельно). Один инстанс на запись manifest.json = на **файл верхнего уровня** или на **подпапку целиком** (подпапка обрабатывается как единый логический источник: агент читает все её файлы из списка `files[]` и пишет один общий `extract.json`).
- **Роль:** requirements extraction specialist. Читает один источник (файл или подпапку) и производит структурированный JSON-экстракт.
- **Вход:** task-файл с записью манифеста (`read_tool`: `read` / `mcp_pdf-reader` / `vision`, плюс `assets`).
- **Логика:** определяет тип документа (transcript / chat / brief / qa / pdf / spreadsheet) по первым ~50 строкам → грузит стратегию `prompts/source_processor/strategies/<type>.md` → читает документ указанным инструментом → извлекает по схеме `prompts/source_processor/output_schema.md`.
- **Выход:** JSON-блок последним элементом ответа (парсит раннер → `extracts/<slug>/extract.json`): `requirements`, `decisions`, `constraints`, `open_questions`, `trust_level`, `source_type_confidence`, при необходимости `needs_clarification` + `clarification_request` (HITL до 2 раундов).
- **Инструменты:** read, pdf-reader MCP, vision.
- **Правила:** не фабриковать требования; неуверенное → `confidence: "low"`.

#### `requirements_writer` — синтез документа требований

- **Фаза:** Extract Phase 2 и ревизии Phase 3.
- **Роль:** senior business analyst. Синтезирует все `extract.json` в единый `_requirements.md` публикационного качества.
- **Вход:** task-файл со списком экстрактов и метаданными проекта.
- **Логика:** читает все экстракты → 1–2 Tavily-поиска на каждую недокументированную внешнюю интеграцию → грузит skill `.github/skills/requirements-template/SKILL.md`, `output_schema.md`, `conflict_rules.md` → пишет документ.
- **Выход:** файл `_requirements.md` (write-инструментом): FR/NFR/BR со сквозной нумерацией и цитированием источников, реестр конфликтов (8.1), реестр пробелов (8.2), допущения (8.3). Без `**bold**` — только GitHub-алерты (`> [!NOTE]` и т.п.).
- **Инструменты:** read, write, tavily.

#### `requirements_critic` — проверка документа требований

- **Фаза:** Extract Phase 3 (цикл с writer, ≤ 5 раундов).
- **Роль:** senior BA / quality reviewer. Проверяет `_requirements.md` по чек-листу S1–S15 (источники у каждого требования, разрешённые конфликты, количественные NFR, полнота секций и пр.) с severity CRITICAL/MAJOR/MINOR.
- **Вход:** task-файл: путь к документу + список экстрактов + путь для verdict.
- **Выход:** файл verdict: `VERDICT: APPROVED` (одна строка) или `VERDICT: REVISE` + findings с секцией, severity и требуемым действием. На REVISE verdict инжектируется в следующий промпт writer'а.
- **Инструменты:** read, write.
- **Порог:** APPROVED = 0 CRITICAL и ≤ 2 MAJOR.

#### `arch_probe` — генерация discovery-вопросов

- **Фаза:** Discovery D1.
- **Роль:** Senior Solution Architect (15+ лет). Анализирует экстракты, оценивает признаки AI-генерации источников (`low/medium/high`), обогащает контекст 3–5 Tavily-поисками (домен, регуляторика, failure modes, паттерны).
- **Выход:** JSON в stdout (парсит раннер): 20–30 «сырых» discovery-вопросов, каждый привязан к конкретному пробелу/противоречию в экстрактах; по схеме `prompts/arch_probe/output_schema.md`.
- **Инструменты:** read, tavily.
- **Критерий качества:** вопрос должен доказывать, что документ прочитан (примеры «плохой/хороший» в промпте агента).

#### `arch_critic` — куратор discovery-отчёта

- **Фаза:** Discovery D2 (финал discovery-пайплайна).
- **Роль:** Principal Architect. Фильтрует сырые вопросы arch_probe: отбраковывает generic/AI-звучащие/ответ уже в документах/составные/снисходительные; переписывает пограничные; отбирает 8–15 вопросов, блокирующих архитектурные решения.
- **Выход:** `discovery_report.md` (write-инструментом) по схеме `prompts/arch_critic/report_schema.md`; язык = язык исходных документов.
- **Инструменты:** read, write.

### 7.2. Пайплайн Solution Design

#### `solution_designer` — генерация проектного решения

- **Фаза:** SD Phase 1 (параллельно, один инстанс на модель из `--models`) и ревизии Phase 3.
- **Роль:** senior solution architect. Из `_requirements.md` производит один целостный технический proposal. Жёсткие правила: **одна архитектура** (никаких меню опций), **никаких оценок** времени/денег/трудозатрат, AI/ML как «позвоночник» документа когда он есть в системе (иначе — та же глубина на реальном ядре системы).
- **Research-дисциплина:** 8–15+ Tavily-поисков по ходу работы — доменный подход, актуальные версии библиотек, паттерны интеграций, NFR-бенчмарки, инфраструктурные сервисы; ничего «из памяти».
- **Структура:** владеет skill `.github/skills/solution-design-template/SKILL.md` (Solution Overview + stakeholder-таблица + Key Innovation 1.3, Technology Stack, Delivery Phasing с Phase 0, NFR-таблица, Infrastructure & Deployment, плейсхолдеры `<!-- ILLUSTRATION: -->`).
- **Выход:** `_design_<model_slug>.md` (write-инструментом); язык = язык требований.
- **Инструменты:** read, write, tavily.

#### `solution_design_selector` — выбор победителя из N кандидатов

- **Фаза:** SD Phase 2 (только если кандидатов ≥ 2).
- **Роль:** технический рефери. Сначала дисквалификаторы (HIGH-нарушения skill'а: мультиопциональность, оценки, отсутствие секций/NFR-таблицы/иллюстраций), затем сравнение HIGH-чистых кандидатов по осям: структура, Key Innovation, сценарии, NFR, grounding, покрытие требований, AI/ML-глубина.
- **Выход:** `_solution_design.md` (победитель **verbatim**, без правок) + `_selection_report.md` с первой строкой `WINNING_MODEL: <model>` и таблицей сравнения + список слабостей победителя для критика.
- **Инструменты:** read, write.
- **Fallback при сбое:** первый успешный кандидант (реализует раннер).

#### `solution_design_critic` — проверка проектного решения

- **Фаза:** SD Phase 3 (цикл с designer победившей модели, ≤ 3 раундов).
- **Роль:** quality gatekeeper. Рубрика — только skill `solution-design-template` (Quality Bar / Severity Mapping / Verdict rules); HIGH: мультиопциональность, любые оценки, пропуски обязательных секций, NFR без механизма, generic Key Innovation; MEDIUM/LOW — по skill'у. Условные (AI/ML-only) проверки применяются только при наличии AI/ML-измерения.
- **Выход:** `_verdict_round<N>.md`: `VERDICT: APPROVED` или `VERDICT: REVISE` + issues в строгом формате `- section: <slug> | severity: HIGH|MEDIUM|LOW | issue: <finding>` с валидными slug'ами секций.
- **Инструменты:** read, write.

### 7.3. Автономные агенты (вне пайплайнов раннеров)

#### `effort_estimator` — оценка трудозатрат по design-документу

- **Триггер:** standalone, после Solution Design.
- **Роль:** senior SA + engagement manager. Из `_solution_design.md` строит `_effort_estimate.md` в формате WBS — **только часы**, без валют и ставок.
- **Контракт:** детерминированная арифметика (рубрика сложности 1–4 → таблица базовых часов на 7 ролей), Phase 0 — фиксированный блок (220 h), Design/Development Stage раздельно в каждой фазе, confidence Min ×0.80 / Mid ×1.00 / Max ×1.30, опциональный `ai_discount` на FE/BE-часы, UX = экраны × 4 h.
- **Выход:** `_effort_estimate.md`: Effort Summary, Phase 0, секции фаз с WBS, Team Composition, Risk Register, Confidence Notes, Extraction Log.
- **Инструменты:** read, write.

#### `word_form_builder` — интерактивная Word-форма уточнений

- **Триггер:** standalone, по результатам discovery/extract.
- **Роль:** RFP Clarification Specialist. Собирает вопросы из Section 7/8 `_requirements.md` и `open_questions` экстрактов → 6–12 вопросов типов `confirm`/`dropdown`/`checkbox_group`/`table` → Tavily-обогащение вариантов ответов → `form_spec.json` → генерация `.docx` скриптом `.github/skills/word-form-builder/scripts/build_word_form.py`.
- **Выход:** `.docx` с нативными чекбоксами/дропдаунами/таблицами + отчёт (путь, размер, число вопросов).
- **Инструменты:** read, write, bash, tavily.

#### `illustrator` — генерация иллюстраций

- **Триггер:** standalone, по плейсхолдерам `<!-- ILLUSTRATION: -->` в design-документе.
- **Роль:** генерация публикационных иллюстраций пакетом PaperBanana (`llmsresearch/paperbanana`, провайдер OpenAI, `gpt-image-2` + референс-датасет автоматически). Пайплайн Retriever → Planner → Stylist → Visualizer ↔ Critic, 3–5 мин на изображение.
- **Ключевые правила:** все иллюстрации запускаются параллельно через фоновый bash; никаких wrapper-скриптов; PNG встраиваются в документ с подписями `Fig. N`; итог — `{project}/illustrations/` + `_manifest.md` с промптами для регенерации; при сбое PaperBanana — репорт ошибки, без fallback на Mermaid/Graphviz.
- **Инструменты:** read, write, bash (background).

#### `confluence_publisher` — публикация в Confluence

- **Триггер:** standalone, публикация финальных Markdown/PDF.
- **Роль:** публикация в Confluence Server/DC **только** через скрипт `.github/skills/confluence-publisher/scripts/publish_to_confluence.py` (PAT Bearer-auth, upsert по title под parent, загрузка PNG-иллюстраций и вложений, Pandoc-конвертация в storage XHTML). MCP-инструменты для вложений запрещены (нет доступа к FS).
- **Выход:** отчёт: title, URL, page ID, версия, число вложений, ошибки.
- **Инструменты:** read, bash (явно в `permission`); Windows-специфика путей учтена в промпте.

---

## 9. Приложение: соответствие агентов режимам вызова

| Агент | Раннер / триггер | Режим вызова | Артефакт |
|---|---|---|---|
| source_processor | requirements_runner Ph1 | JSON из ответа | `extracts/<slug>/extract.json` |
| requirements_writer | requirements_runner Ph2/Ph3 | файл | `_requirements.md` |
| requirements_critic | requirements_runner Ph3 | файл | `verdict.md` (r<N>) |
| arch_probe | requirements_runner D1 | JSON из ответа | raw questions JSON |
| arch_critic | requirements_runner D2 | файл | `discovery_report.md` |
| solution_designer | solution_design_runner Ph1/Ph3 | файл | `_design_<model>.md` |
| solution_design_selector | solution_design_runner Ph2 | файл | `_solution_design.md`, `_selection_report.md` |
| solution_design_critic | solution_design_runner Ph3 | файл | `_verdict_round<N>.md` |
| effort_estimator | standalone | файл | `_effort_estimate.md` |
| word_form_builder | standalone | файл + bash-скрипт | `.docx` форма |
| illustrator | standalone | bash + файлы PNG | `illustrations/`, `_manifest.md` |
| confluence_publisher | standalone | bash-скрипт | Confluence page |
