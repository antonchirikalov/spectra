# План переноса spectra на архитектуру opencode serve + API

Версия: 1.0
Дата: 2026-07-17
Базовая спека: `docs/SPEC_SERVE_API.md`
Статус: утверждён к исполнению

---

## 0. Рамки работ (scope)

### В scope

Два раннера и восемь пайплайн-агентов, которые они вызывают:

| Раннер | Агенты |
|---|---|
| `requirements_runner.py` (Extract + Discovery) | source_processor, requirements_writer, requirements_critic, arch_probe, arch_critic |
| `solution_design_runner.py` | solution_designer, solution_design_selector, solution_design_critic |

### Вне scope (решение от 2026-07-17)

- **effort_estimator** — не переносим.
- **word_form_builder** — не переносим.

Оба — standalone-агенты: вызываются вручную через opencode CLI/TUI, а не раннерами, поэтому миграция транспорта их физически не затрагивает. Их `.md`-определения не меняются, работают как сегодня.

Также не затрагиваются по той же причине: **illustrator**, **confluence_publisher** (тоже standalone).

---

## 1. Принципы переноса

1. **Транспорт за флагом.** Новый флаг `--transport subprocess|serve`. Пока этап не закрыт — default `subprocess`; после стабилизации — `serve`. Это даёт мгновенный rollback и A/B-сравнение на одном входе.
2. **Фасад над вызовами.** Сигнатуры `run_agent()` / `run_agent_write()` сохраняются; внутри — диспетчер по `--transport`. Логика фаз, critic-циклов и ledger не трогается.
3. **Golden-run приёмка.** Один фиксированный тестовый вход (малый реальный проект: 2–3 источника, включая PDF). Прогон старым и новым транспортом, сравнение артефактов **структурно** (не побайтово — LLM недетерминирован): наличие `extract.json` по каждому источнику, валидность JSON, наличие обязательных секций в `_requirements.md`, вердикт критика.
4. **Мёртвый код удаляем только после стабилизации** serve-транспорта (минимум 3 зелёных прогона Extract + 1 SD).

---

## 2. Этапы

### Этап 0 — Разведка API (0.5 дня)

Цель: заменить все «уточняется по /doc» в спеке на проверенные факты.

- 0.1. Запустить `opencode serve --port 4096` из корня spectra; сохранить спеку: `GET http://127.0.0.1:4096/doc` → `docs/openapi/opencode-1.18.3.json`.
- 0.2. Spike руками (httpx/curl):
  - `GET /global/health` — формат ответа, поле version;
  - `GET /agent` — наши 12 агентов видны серверу;
  - `GET /mcp` — статусы pdf-reader / tavily-remote / mcp-atlassian / docx-mcp;
  - `POST /session` → `POST /session/:id/message` с `agent=source_processor`, `model` — **зафиксировать точный шейп model** (`{providerID, modelID}` vs строка);
  - `GET /event` (SSE) во время прогона — **зафиксировать типы событий**: старт/стоп шага, tool call начало/конец, ошибка провайдера, permission-запрос, финальное сообщение;
  - `POST /session/:id/abort` — поведение при живом шаге.
- 0.3. Дополнить `SPEC_SERVE_API.md` §3.2/§3.3 проверенными шейпами и таблицей SSE-событий → маппинг на `error_kind` (timeout / api / process / no_json).
- 0.4. Проверить известный баг #6573 не воспроизводится на нашей конфигурации (наши агенты не спавнят Task-сабагентов — ожидаемо чисто).

**Выход:** обновлённая спека, список событий для детекции, подтверждённый end-to-end вызов одного агента.

### Этап 1 — Модуль `opencode_client.py` (1 день)

- 1.1. `OpencodeServer.start(port=0)`: `subprocess.Popen(["opencode", "serve", ...], cwd=REPO_ROOT)` → опрос `GET /global/health` до ready (≤ 30 с) → сверка `version` с поддерживаемой (warn при расхождении).
- 1.2. Sanity-check при старте: `GET /agent` ⊇ нужные агенты; `GET /mcp` — все `connected`; иначе — понятная ошибка до начала фаз.
- 1.3. `run_step(agent, model, prompt, slug, timeout_s, on_event=None, permission_handler=None) -> StepResult`:
  - новая сессия на вызов; `POST /session/:id/message` блокирующе;
  - фоновый SSE-reader: heartbeat с текущим tool call (`[slug] running… tool: read_pdf (45s)`), классификация ошибок по типизированным событиям, permissions → handler (default: auto-approve — паритет с `--dangerously-skip-permissions`);
  - client-side timeout → `POST /session/:id/abort` → `error_kind="timeout"`;
  - сбор финального assistant-текста из parts ответа.
- 1.4. `OpencodeServer.stop()`: `POST /instance/dispose`, fallback — terminate; гарантированный вызов в `finally` раннера.
- 1.5. Тесты на записанных ответах спеки (без живого сервера): маппинг событий, abort-ветка, сбор текста.

**Выход:** модуль + тесты; `requirements.txt` +`httpx` (проверить наличие).

### Этап 2 — `requirements_runner.py` (1–2 дня)

- 2.1. CLI: `--transport subprocess|serve` (default `subprocess`); проброс в оба режима `run`/`resume`.
- 2.2. Фасад: `run_agent()`/`run_agent_write()` диспетчерят по транспорту; serve-ветка — адаптер к `OpencodeServer.run_step()`, сохраняющий `AgentResult` и `(bool, event_log)`.
- 2.3. Lifecycle: сервер поднимается в `main()` один раз на прогон (и на `resume`); `stop()` в `finally`.
- 2.4. `state.json`: + `session_id` на шаг; команда `status` показывает его.
- 2.5. Прогоны golden-run:
  - Extract serve vs subprocess — структурное сравнение `extract.json` и `_requirements.md`; critic-цикл до APPROVED на новом транспорте;
  - Discovery serve — `discovery_report.md` создаётся, 8–15 вопросов;
  - Краш-тест: kill раннера в середине Phase 1 → `resume` доводит до конца (шаги `running→pending` как раньше).
- 2.6. Retry-семантика сохранена: новая сессия на попытку, пауза 2 с, `max_retries`.

**Критерий выхода:** 3 зелёных прогона Extract (включая 1 с ревизией критика) + 1 Discovery + 1 crash-resume.

### Этап 3 — `solution_design_runner.py` (0.5–1 день)

- 3.1. Тот же флаг и фасад (общий код — в `opencode_client.py`, без копипасты).
- 3.2. Прогон SD с двумя моделями (`kimi/kimi-k3` + одна запасная): selector отрабатывает, `_selection_report.md` с `WINNING_MODEL:`, critic-цикл до APPROVED или cap.

**Критерий выхода:** 1 зелёный прогон с 2 моделями на golden-входе.

### Этап 4 — Зачистка и релиз (0.5 дня)

- 4.1. Default `--transport serve`; subprocess остаётся fallback на один цикл релизов.
- 4.2. Удаление мёртвого кода после стабилизации: `_opencode_env()`, `_run_with_heartbeat()`, `_detect_api_error()`, резолв `OPENCODE_EXE` (из serve-ветки).
- 4.3. Документы: `README.md` + `README_RU.md` (архитектура, отладка через `opencode attach`, новый флаг), статус в `SPEC_SERVE_API.md` → «реализовано», ссылка на этот план.
- 4.4. Заметка в плане: отдельной фичей позже — watchdog-перезапуск сервера, permissions через API вместо skip-флага, async fan-out вместо потоков.

---

## 3. Тестовая стратегия

| Уровень | Что | Как |
|---|---|---|
| Unit | opencode_client | записанные ответы спеки, без сервера |
| Contract | шейпы API | spike этапа 0, спека `/doc` в репо (`docs/openapi/`) |
| Golden-run | Extract / Discovery / SD end-to-end | фиксированный вход; структурное сравнение артефактов двух транспортов |
| Краш | resume | kill раннера в Phase 1 → resume до конца |
| Регрессия | subprocess-транспорт | остаётся доступным до конца стабилизации |

Недетерминизм LLM: артефакты двух прогонов сравниваются по структуре (ключи JSON, секции, вердикты), не по тексту.

## 4. Откат

Любой этап откатывается флагом `--transport subprocess` без изменения кода пайплайнов. Полный откат = удаление флага и serve-ветки (git revert), ledger и артефакты совместимы в обе стороны.

## 5. Оценка

| Этап | Оценка |
|---|---|
| 0 — разведка API | 0.5 дня |
| 1 — opencode_client.py | 1 день |
| 2 — requirements_runner | 1–2 дня |
| 3 — solution_design_runner | 0.5–1 день |
| 4 — зачистка | 0.5 дня |
| **Итого** | **3.5–5 дней** |

## 6. Открытые вопросы — ЗАКРЫТЫ spike'ом 2026-07-17

Этап 0 выполнен (`scripts/spike_serve_api.py`, opencode 1.18.3). Результаты зафиксированы в `SPEC_SERVE_API.md` §3.9; спека и события — в `docs/openapi/`.

- ✅ Шейп `model`: объект `{"providerID": "kimi", "modelID": "kimi-k3"}` — HTTP 200.
- ✅ SSE: конверт `{id, type, properties}`, фильтр по `properties.sessionID`; типы событий и маппинг на `error_kind` — в спеке §3.9.
- ✅ Ошибки: типизированный `session.error {error: {name, data: {message}}}` — regex не нужен; abort подтверждается `MessageAbortedError`.
- ✅ parentID: поддерживается — сессии прогона группируем под корневой `run-<run_id>`.
- ✅ Все 12 агентов spectra видны через `GET /agent`; нужные MCP — connected.
- ✅ K3 работает через API: тестовый вызов `kimi/kimi-k3` → 200 OK.
- ⚠️ github MCP — failed (OAuth, предсуществующее; пайплайнам не нужен).

Бонус-находка: ответ `/message` содержит `info.tokens` и `info.cost` — можно писать стоимость каждого шага в `state.json` (учёт стоимости прогона, чего не было в subprocess).
