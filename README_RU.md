# spectra

**spectra** принимает папку с сырыми клиентскими документами — RFP, предложения, записи встреч, PDF, таблицы, изображения — и превращает их в готовые технические артефакты: структурированную спецификацию требований, подборку вопросов для архитектурной сессии и полноценное предложение по решению. Кладёте файлы, пайплайн запускается, документы выходят.

Внутри — многоагентная AI-система. Агенты **opencode** CLI занимаются чтением и написанием документов — работает любая модель от любого провайдера: Kimi K2.6, DeepSeek, GPT-4o, Claude, Qwen или локальная модель через Ollama. Python-оркестраторы управляют выполнением — порядком фаз, параллелизмом, восстановлением после сбоев и логикой повторов. Все передачи между фазами — это файлы на диске, поэтому любой шаг можно возобновить после сбоя без повторного запуска уже выполненных этапов.

Три пайплайна, одна входная папка:

| Пайплайн | Оркестратор | Вход | Выход | Когда использовать |
|---|---|---|---|---|
| **Extract** | `requirements_runner.py` | Сырые документы | `_requirements.md` | Структурированная спецификация FR/NFR/BR из неструктурированных источников |
| **Discovery** | `requirements_runner.py --mode discovery` | Сырые документы | `discovery_report.md` | Подборка архитектурных вопросов перед воркшопом |
| **Solution Design** | `solution_design_runner.py` | `_requirements.md` | `_solution_design.md` | Полное техническое предложение по решению из спецификации |

---

## Пайплайны

![Рис. 1. Три пайплайна: Extract, Discovery, Solution Design](docs/illustrations/pipelines.png)

*Рис. 1. Три пайплайна — Extract, Discovery и Solution Design — все управляются Python-оркестраторами. Extract и Discovery разделяют Фазу 0 и Фазу 1 (параллельное извлечение из источников). Solution Design принимает готовый документ с требованиями на вход.*

Два режима, одна входная папка:

| Режим | Флаг | Выход | Когда использовать |
|---|---|---|---|
| `extract` | `--mode extract` (по умолчанию) | `_requirements.md` — FR / NFR / BR / конфликты / пробелы | Структурированная спецификация из сырых источников |
| `discovery` | `--mode discovery` | `discovery_report.md` — подборка архитектурных вопросов | Перед воркшопом; когда нужно найти, чего не хватает |

---

## Быстрый старт

### macOS / Linux

```bash
# Клонировать и настроить
git clone <repo>
cd spectra
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# Настроить окружение
cp .env.example .env
# → добавить хотя бы один ключ провайдера (MOONSHOT_API_KEY, OPENAI_API_KEY, DEEPSEEK_API_KEY, …)

# Запустить извлечение требований
.venv/bin/python3 requirements_runner.py run /путь/до/папки/с/документами

# Запустить в режиме Discovery
.venv/bin/python3 requirements_runner.py run /путь/до/папки/с/документами --mode discovery

# Запустить Solution Design (после извлечения)
.venv/bin/python3 solution_design_runner.py run \
  /путь/до/requirements_YYYYMMDD_HHMMSS/_requirements.md

# Запустить Solution Design с несколькими моделями (параллельно)
.venv/bin/python3 solution_design_runner.py run \
  /путь/до/requirements_YYYYMMDD_HHMMSS/_requirements.md \
  --models kimi/kimi-k3 openai/gpt-4o

# Проверить статус запуска
.venv/bin/python3 requirements_runner.py status \
  /путь/до/requirements_YYYYMMDD_HHMMSS

# Возобновить прерванный запуск
.venv/bin/python3 requirements_runner.py resume \
  /путь/до/requirements_YYYYMMDD_HHMMSS

# Возобновить и повторить все упавшие шаги
.venv/bin/python3 requirements_runner.py resume \
  /путь/до/requirements_YYYYMMDD_HHMMSS --retry-failed

# Принудительно перезапустить конкретный шаг
.venv/bin/python3 requirements_runner.py resume \
  /путь/до/requirements_YYYYMMDD_HHMMSS --force-step critic:r2
```

### Windows (CMD / PowerShell)

```powershell
# Клонировать и настроить
git clone <repo>
cd spectra
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt

# Настроить окружение
copy .env.example .env
# → добавить хотя бы один ключ провайдера (MOONSHOT_API_KEY, OPENAI_API_KEY, DEEPSEEK_API_KEY, …)

# Запустить извлечение требований
.venv\Scripts\python requirements_runner.py run C:\путь\до\папки\с\документами

# Использовать конкретную модель
.venv\Scripts\python requirements_runner.py run C:\путь\до\папки\с\документами --model openai/gpt-4.1

# Ограничить параллелизм (по умолчанию 3)
.venv\Scripts\python requirements_runner.py run C:\путь\до\папки\с\документами --workers 2

# Запустить в режиме Discovery
.venv\Scripts\python requirements_runner.py run C:\путь\до\папки\с\документами --mode discovery

# Запустить Solution Design (после извлечения)
.venv\Scripts\python solution_design_runner.py run `
  C:\путь\до\requirements_YYYYMMDD_HHMMSS\_requirements.md

# Проверить статус запуска
.venv\Scripts\python requirements_runner.py status `
  C:\путь\до\requirements_YYYYMMDD_HHMMSS

# Возобновить прерванный запуск
.venv\Scripts\python requirements_runner.py resume `
  C:\путь\до\requirements_YYYYMMDD_HHMMSS --retry-failed
```

---

## Установка

### Зависимости

- Python 3.11+
- [opencode](https://opencode.ai) CLI — `brew install anomalyco/tap/opencode`
- Ключ хотя бы одного AI-провайдера (см. таблицу ниже)

### Переменные окружения

```bash
cp .env.example .env
```

Заполните `.env` — добавьте ключи нужных провайдеров:

| Провайдер | Переменная | Модели | Примечание |
|---|---|---|---|
| Moonshot | `MOONSHOT_API_KEY` | `kimi/kimi-k3` | По умолчанию — лучший agentic-бенчмарк |
| OpenAI | `OPENAI_API_KEY` | `openai/gpt-4o`, `openai/gpt-4.1` | Хорошо для агентов-критиков |
| DeepSeek | `DEEPSEEK_API_KEY` | `deepseek/deepseek-chat`, `deepseek/deepseek-reasoner` | Дешевле всего для больших объёмов |
| Qwen | `QWEN_API_KEY` | `qwen/qwen3.6-plus` | Контекст 1M, большие наборы документов |
| Anthropic | `ANTHROPIC_API_KEY` | `anthropic/claude-sonnet-4-6` | Через CLI `claude` |
| Fireworks | `FIREWORKS_API_KEY` | `kimi/kimi-k3`, любые open-weight | US-хостинг, соответствие data residency |

Для интеграций добавьте:
```
CONFLUENCE_TOKEN=...   # Confluence MCP
JIRA_TOKEN=...         # Jira MCP
```

### MCP-серверы (опционально, но рекомендуется)

| Сервер | Назначение | Нужен для |
|---|---|---|
| `pdf-reader` | Чтение PDF напрямую | Исходные PDF-файлы |
| `tavily-remote` | Веб-поиск в процессе работы | arch_probe, solution_designer |
| `mcp-atlassian` | Загрузка страниц Confluence по URL | Источники в Confluence |

Настраиваются в `opencode.json` — при необходимости скорректируйте пути под свою систему.

### Замечания для Windows

Раннер принудительно использует UTF-8 для `print()` и вывода подпроцессов. Если в консоли всё ещё возникают `UnicodeEncodeError` или кракозябры, переключите кодовую страницу перед запуском:

```cmd
chcp 65001
set PYTHONIOENCODING=utf-8
.venv\Scripts\python requirements_runner.py run C:\путь\до\входных_данных
```

### Оплата провайдеров

- **Moonshot / Kimi:** подписка на `kimi.com` **не равна** балансу API на `platform.moonshot.ai`. `opencode` расходует именно **API-баланс** на `platform.moonshot.ai`. Пополняйте его, если видите ошибки 401/429.
- **OpenAI:** баланс расходуется со стандартной страницы биллинга OpenAI API.

Раннер распознаёт ошибки API, которые выдаёт `opencode` (например, `database is locked`, 401/429), и помечает шаг как упавший вместо того, чтобы висеть до таймаута.

---

## Входные данные

Поместите любую комбинацию файлов в папку и передайте её в `requirements_runner.py run`:

| Тип файла | Способ чтения |
|---|---|
| `.pdf` | MCP-инструмент `pdf-reader` |
| `.xlsx` | MCP-сервер `excel` |
| `.docx` / `.pptx` | `docx-mcp` / инструмент `read` |
| `.md` / `.txt` | Инструмент `read` |
| `.png` / `.jpg` / `.jpeg` / `.webp` | Vision (мультимодальность) |
| Подпапки | Один логический источник (один агент на папку) |
| `.txt` с URL | Confluence через MCP или прямой `webfetch` |

Исключаются автоматически: `plan/`, `.git/`, `.github/`, `__pycache__/`, `outputs/`.

---

## Структура выходных данных

Каждый запуск создаёт самодостаточную папку с временной меткой рядом с входной:

```
project/
  input/                                  ← исходные документы (не изменяются)
  requirements_20260604_152709/           ← результат запуска
    _requirements.md                      ← финальный документ
    plan/
      params.yaml                         ← переопределения моделей, политика доверия
    state.json                            ← надёжный журнал состояния
    _artifacts_20260604_152709/
      runner.log
      intake/
        manifest.json                     ← список отсканированных источников
      extracts/
        <slug>/
          extract.json                    ← структурированный вывод по источнику
          raw.txt                         ← сырой ответ агента
          agent.events.jsonl              ← поток событий opencode
        _requirements_writer/
          agent.events.jsonl
        _requirements_critic_r1/
          verdict.md                      ← VERDICT: APPROVED / REVISE
          agent.events.jsonl
      prompts/
        <slug>.md                         ← промпт-задание для каждого агента
        _requirements_writer.md
        _requirements_critic_r1.md
```

Выход Solution Design:

```
project/
  requirements_20260604_152709/
    _requirements.md                      ← вход (не изменяется)
  solution_design_20260604_160312/
    _solution_design.md                   ← финальный документ
    _design_kimi_kimi-k3.md             ← кандидат Фазы 1
    _design_openai_gpt-4o.md              ← кандидат Фазы 1 (при --models)
    _selection_report.md                  ← WINNING_MODEL: ...
    _verdict_round1.md                    ← вердикт критика
    state.json
    prompts/
    logs/
```

---

## Детали пайплайнов

### Режим Extract

![Рис. 2. Пайплайн Extract — сканирование, параллельное извлечение, синтез, цикл критика](docs/illustrations/extract_pipeline.png)

*Рис. 2. Пайплайн Extract — сканирование, параллельное извлечение, синтез, цикл критика.*

```
Фаза 0 → Фаза 1 (параллельно) → Фаза 2 → Фаза 3 (цикл)
  скан     source_processor       writer    critic ↔ writer
```

#### Фаза 0 — Сканирование + Манифест

`requirements_runner.py` обходит входную папку, классифицирует каждый элемент по типу и строит `manifest.json`. Каждая запись получает slug, вид (`file` / `subfolder`) и подходящий `read_tool`.

#### Фаза 1 — Параллельное извлечение из источников

По одному агенту `source_processor` на каждую запись манифеста, все запускаются одновременно через `ThreadPoolExecutor`. Каждый агент:

- определяет тип документа (транскрипт / чат / бриф / PDF / таблица / QA)
- загружает соответствующую стратегию извлечения из `prompts/source_processor/strategies/`
- выводит `extract.json` с: `requirements`, `decisions`, `constraints`, `open_questions`, `trust_level`

Heartbeat каждые 10 секунд (теперь с понятным label):
```
[09:01:10] [rfp-doc — rfp.pdf] start
[09:01:20] [rfp-doc — rfp.pdf] running... 10s elapsed, timeout in 3590s
[09:02:03] [rfp-doc — rfp.pdf] done
```

**HITL:clarify** (при `--interactive`): если агент возвращает `needs_clarification: true`, оркестратор ставится на паузу и ждёт ответа в терминале. Агент перезапускается с уточнением. До 2 раундов уточнений.

#### Фаза 2 — Requirements Writer

`requirements_writer` читает все успешные `extract.json` и синтезирует `_requirements.md`:

- Функциональные требования (FR-001, FR-002, …)
- Нефункциональные требования (NFR-001, …)
- Бизнес-требования (BR-001, …)
- Реестр конфликтов — противоречия между источниками
- Реестр пробелов — неотвеченные вопросы
- Допущения

Валидация перед продолжением: должны присутствовать заголовок `# Requirements:` и хотя бы одна запись `FR-`.

#### Фаза 3 — Цикл Критик ↔ Писатель

`requirements_critic` проверяет `_requirements.md` по источникам и пишет вердикт:

```
VERDICT: APPROVED
```
или
```
VERDICT: REVISE
- Раздел 2.1: отсутствует NFR по времени отклика
- Конфликт FR-004 vs FR-017 не разрешён
```

При `REVISE` — вердикт вставляется в следующий промпт писателя и `requirements_writer` делает ревизию. Повторяется до **`APPROVED`** или предохранительного ограничения в **5 раундов** (`MAX_CRITIC_ROUNDS`). Достижение лимита — предупреждение, не ошибка.

---

### Режим Discovery

```
Фаза 0 → Фаза 1 (параллельно) → Фаза D1 → Фаза D2
  скан     source_processor        probe      critic
```

Фазы 0 и 1 идентичны режиму Extract.

**Фаза D1 — arch_probe**: читает все `extract.json`, выполняет веб-поиск через Tavily для контекста, генерирует **20–30 сырых вопросов**, привязанных к конкретным пробелам.

**Фаза D2 — arch_critic**: отбирает вопросы до **8–15**, без ответа на которые невозможно принять архитектурные решения. Пишет `discovery_report.md` напрямую.

---

### Пайплайн Solution Design

![Рис. 3. Пайплайн Solution Design — параллельная генерация несколькими моделями, отбор, цикл критика](docs/illustrations/solution_design_pipeline.png)

*Рис. 3. Пайплайн Solution Design — параллельная генерация несколькими моделями, отбор, цикл критика.*

```
Фаза 1 (параллельно) → Фаза 2 → Фаза 3 (цикл) → Фаза 4
  N × solution_designer   selector   critic ↔ designer   итог
```

#### Фаза 1 — Параллельная генерация

По одному агенту `solution_designer` на каждую модель, все запускаются одновременно. Каждый производит `_design_<model_slug>.md` — полный дизайн решения в одной зафиксированной архитектуре. Никаких меню выбора, никаких оценок трудоёмкости.

По умолчанию: `kimi/kimi-k3`. Переопределение:

```bash
# Два дизайна параллельно
python3 solution_design_runner.py run _requirements.md \
  --models kimi/kimi-k3 openai/gpt-4o

# Три дизайна параллельно
python3 solution_design_runner.py run _requirements.md \
  --models kimi/kimi-k3 openai/gpt-4o openai/gpt-4.1
```

Если одна из моделей упала, пайплайн продолжает работу с остальными.

#### Фаза 2 — Отбор

Один кандидат → копируется как `_solution_design.md`.

Несколько кандидатов → `solution_design_selector` читает всех и выбирает сильнейшего. Пишет `_selection_report.md` со строкой `WINNING_MODEL: <модель>` в начале. Если selector упал: используется первый успешный кандидат.

#### Фаза 3 — Цикл Критика

`solution_design_critic` проверяет `_solution_design.md` по шаблону требований (`.github/skills/solution-design-template/SKILL.md`) и пишет вердикт. При `REVISE` — дизайнер с победившей моделью запускает ревизию. Предохранительный лимит: **3 раунда**.

#### Фаза 4 — Итог

Печатает пути ко всем артефактам, победившую модель, финальный вердикт и количество плейсхолдеров `<!-- ILLUSTRATION: -->` для агента Illustrator.

---

## Справка по CLI

### `requirements_runner.py`

| Подкоманда | Аргумент | По умолчанию | Описание |
|---|---|---|---|
| `run` | `project_dir` | — | Путь к папке с исходными документами |
| `run` | `--mode` | `extract` | `extract` или `discovery` |
| `run` | `--model` | `kimi/kimi-k3` | Переопределить модель для всех агентов |
| `run` | `--workers` | 3 | Максимальное число параллельных `source_processor` |
| `run` | `--interactive` | выкл | Остановка на HITL-контрольных точках |
| `run` | `--debug` | выкл | Логирование уровня DEBUG в stderr |
| `resume` | `--model` | — | Переопределить модель при возобновлении |
| `resume` | `--workers` | 3 | Параллелизм для оставшихся extract-шагов |
| `status` | `output_dir` | — | Таблица шагов: статус, время, попытки, артефакт/ошибка |
| `resume` | `output_dir` | — | Продолжить с места остановки |
| `resume` | `--retry-failed` | выкл | Сбросить все `failed` шаги в `pending` |
| `resume` | `--force-step STEP_ID` | — | Принудительно сбросить один шаг (напр. `critic:r2`) |

### `solution_design_runner.py`

| Подкоманда | Аргумент | По умолчанию | Описание |
|---|---|---|---|
| `run` | `requirements_path` | — | Путь до `_requirements.md` |
| `run` | `--models MODEL [...]` | `kimi/kimi-k3` | Модели для параллельной Фазы 1 |
| `run` | `--verbose` / `-v` | выкл | Логирование DEBUG в stderr |
| `status` | `output_dir` | — | Показать таблицу шагов |
| `resume` | `output_dir` | — | Продолжить прерванный запуск |
| `resume` | `--retry-failed` | выкл | Сбросить упавшие шаги |
| `resume` | `--force-step STEP_ID` | — | Принудительно сбросить один шаг (напр. `selector`, `critic:r2`) |

### ID шагов (для `--force-step`)

| Оркестратор | Шаблон ID | Пример |
|---|---|---|
| requirements | `extract:<slug>` | `extract:rfp-doc` |
| requirements | `phase2:requirements_writer` | |
| requirements | `critic:r<n>` | `critic:r2` |
| requirements | `revision:r<n>` | `revision:r1` |
| solution design | `designer-<model-slug>` | `designer-kimi_kimi-k3` |
| solution design | `selector` | |
| solution design | `critic:r<n>` | `critic:r1` |
| solution design | `revision:r<n>` | `revision:r2` |

---

## Восстановление после сбоя

`state.json` записывается атомарно после каждого шага (`tmp → os.replace`). Любой шаг со статусом `running` при запуске автоматически сбрасывается в `pending`.

```bash
# Посмотреть что произошло
python3 requirements_runner.py status output_dir/

# Продолжить — выполненные шаги пропускаются
python3 requirements_runner.py resume output_dir/

# Повторить всё, что упало
python3 requirements_runner.py resume output_dir/ --retry-failed

# Принудительно перезапустить один шаг
python3 requirements_runner.py resume output_dir/ --force-step critic:r2
```

---

## Маршрутизация моделей

Все модели используют формат `провайдер/model-id`. Оркестратор передаёт это значение в `opencode run --model`. Провайдеры определяются в `opencode.json`.

### Переопределение моделей по агентам (`plan/params.yaml`)

Генерируется автоматически при первом запуске. Редактируйте для назначения конкретных моделей конкретным агентам:

```yaml
# Kimi везде (по умолчанию)
models: {}

# Оптимизация стоимости: DeepSeek для объёма, Kimi для качества
models:
  source_processor:         deepseek/deepseek-chat   # дёшево, большой объём
  arch_probe:               kimi/kimi-k3
  requirements_writer:      kimi/kimi-k3
  requirements_critic:      deepseek/deepseek-chat
  solution_designer:        kimi/kimi-k3
  solution_design_critic:   openai/gpt-4o            # сильный критик

# Смешанный: Kimi + Claude на критически важных агентах
models:
  source_processor:         deepseek/deepseek-chat
  requirements_writer:      anthropic/claude-sonnet-4-6
  requirements_critic:      anthropic/claude-sonnet-4-6
  solution_designer:        kimi/kimi-k3
  solution_design_critic:   anthropic/claude-sonnet-4-6
```

Пустой `models: {}` → все агенты используют `DEFAULT_MODEL = kimi/kimi-k3`.

### Добавление провайдера

Добавьте один блок в `opencode.json`:

```json
"deepseek": {
  "npm": "@ai-sdk/openai-compatible",
  "name": "DeepSeek",
  "options": {
    "baseURL": "https://api.deepseek.com/v1",
    "apiKey": "{env:DEEPSEEK_API_KEY}"
  },
  "models": {
    "deepseek-chat": { "name": "DeepSeek V4" }
  }
}
```

Добавьте переменную в `.env`, ссылайтесь как `deepseek/deepseek-chat` в `params.yaml`. Изменений в коде не требуется.

---

## Агенты

| Агент | Запускается | Инструменты | Назначение |
|---|---|---|---|
| `source_processor` | Фаза 1 | read, pdf-reader, vision | Извлекает JSON с требованиями из одного источника |
| `requirements_writer` | Фаза 2, ревизии Фазы 3 | read, edit, tavily | Синтезирует извлечения → `_requirements.md` |
| `requirements_critic` | Фаза 3 | read, edit | Проверяет и выносит вердикт APPROVED / REVISE |
| `arch_probe` | Discovery D1 | read, tavily | Генерирует 20–30 сырых вопросов |
| `arch_critic` | Discovery D2 | read, edit | Отбирает 8–15 блокирующих вопросов |
| `solution_designer` | SD Фаза 1, ревизии | read, edit, tavily | Полный дизайн решения в одной архитектуре |
| `solution_design_selector` | SD Фаза 2 | read, edit | Выбирает сильнейший дизайн из N кандидатов |
| `solution_design_critic` | SD Фаза 3 | read, edit | Проверяет дизайн; вердикт APPROVED / REVISE |
| `effort_estimator` | Отдельно | read, edit | WBS-оценка трудоёмкости в часах |
| `word_form_builder` | Отдельно | read, edit, bash, tavily | Интерактивная форма уточнений в Word `.docx` |

Определены в `.opencode/agents/` — opencode находит их автоматически из корня проекта.
