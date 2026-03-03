# План развития проекта: отказ от LangChain, своё управление ИИ

Цель: полностью убрать LangChain и заменить его на явное управление вызовами LLM, памятью и инструментами (MCP) через собственный код.

---

## Текущее использование LangChain

| Место | Что используется | Назначение |
|-------|-------------------|------------|
| `agent/ai_client.py` | `AgentExecutor`, `create_tool_calling_agent`, `hub.pull`, `ConversationBufferMemory`, `ChatGoogleGenerativeAI` | Агент с вызовом инструментов, промпт с Hub, память чата |
| `core/services.py` | `ConversationSummaryBufferMemory`, `ChatGoogleGenerativeAI`, `ChatGroq` | Память с суммаризацией для контекста чата, LLM для суммаризации |
| `interface/gui/worker.py` | `load_mcp_tools` (langchain_mcp_adapters) | Преобразование MCP-инструментов в формат LangChain |
| `tools/code_interpreter.py` | `@tool`, `ChatGoogleGenerativeAI` | Описание инструмента, генерация кода (сейчас не в основном потоке) |

---

## Общая идея замены

1. **LLM** — вызывать Google Generative AI (Gemini) напрямую через официальный SDK `google-generativeai`, без `langchain_google_genai`.
2. **Память чата** — свой формат: список сообщений `[{role, parts}]` из БД (`MessageService`), при необходимости обрезка/суммаризация своим вызовом LLM.
3. **Инструменты** — получать список из MCP (`MCPClient.get_tools()`), конвертировать в схему Gemini (Function Calling), в цикле: ответ модели → парсинг `function_call` → вызов `session.call_tool()` → добавление результата в историю → повторный вызов LLM до финального текстового ответа.
4. **Агент** — один класс (например, `agent/orchestrator.py`): метод `ask(user_message)` реализует цикл (запрос → ответ → вызов инструментов → повтор), без AgentExecutor и без LangChain.

---

## Память: short-term vs long-term (и где нужна векторная)

**Short-term (текущий чат, последние реплики)**  
- Нужен **порядок**: сообщение 1 → 2 → 3.  
- Достаточно **скользящего окна**: последние N сообщений (или N токенов) из БД в хронологическом порядке.  
- **Векторный поиск здесь не лучше**: он возвращает по сходству, а не по времени — порядок нарушается. Плюс лишние эмбеддинги и поиск на каждый запрос без выигрыша.

**Long-term (между чатами, факты о пользователе)**  
- Нужно **находить по смыслу**: «что пользователь говорил про X», «в каких чатах обсуждали проект Y».  
- Здесь **векторная память уместна**: храним эмбеддинги фрагментов (или суммариев чатов), по запросу достаём top-K релевантных и подмешиваем в контекст.

**Итого:**  
- **Short-term** — оставить хронологическое окно из БД (последние N сообщений текущего чата), без векторов.  
- **Long-term** — добавить векторное хранилище отдельной фазой: эмбеддинги прошлых сообщений/суммариев, семантический поиск при сборке контекста (опционально, см. Фаза 5).

---

## Фазы плана

### Фаза 1: Прямой клиент Gemini (без LangChain)

**Задачи:**

1. Добавить зависимость: `google-generativeai` (официальный SDK).
2. Создать модуль `core/llm_client.py`:
   - Класс `GeminiClient` с методом `generate(messages, tools=None)`.
   - Вход: список сообщений в формате Gemini (role + parts), опционально список инструментов (FunctionDeclaration).
   - Выход: объект ответа с полями `text` и `function_calls` (если модель запросила вызов инструментов).
3. Конфиг оставить в `config/settings.py`: `GENAI_API_KEY`, `GENAI_MODEL` (без привязки к LangChain).
4. В `agent/mcp_client.py` убрать использование `ChatGoogleGenerativeAI` (если останется только MCP — оставить только сессию MCP).

**Результат:** один способ генерации текста через Gemini без LangChain.

---

### Фаза 2: Собственная «память» чата

**Задачи:**

1. В `core/services.py` убрать `ConversationSummaryBufferMemory`, `ChatGroq`, `ChatGoogleGenerativeAI`.
2. В `AIClientService.load_memory_for_chat(chat_id)`:
   - Читать историю из `message_db.get_messages_by_chat_id(chat_id)`.
   - Возвращать не LangChain-память, а список сообщений в формате для Gemini, например:  
     `[{"role": "user", "parts": [{"text": "..."}]}, {"role": "model", "parts": [{"text": "..."}]}, ...]`.
3. При длинной истории (например, лимит токенов ~8k–32k):
   - Вариант A: обрезать старые сообщения, оставляя последние N пар user/model.
   - Вариант B (опционально): отдельный вызов `GeminiClient.generate` с промптом «Кратко суммаризуй диалог» и подставлять суммаризацию в начало контекста (без LangChain).

**Результат:** контекст чата формируется из БД и передаётся в `GeminiClient.generate` как список сообщений.

---

### Фаза 3: Конвертация MCP → Gemini и цикл вызова инструментов

**Задачи:**

1. В `agent/mcp_client.py` оставить только работу с MCP: `connect_to_server`, `get_tools()`, `session.call_tool(name, arguments)`.
2. Добавить модуль `agent/tools_adapter.py`:
   - Функция `mcp_tools_to_gemini_declarations(mcp_tools)` — преобразование списка MCP Tool в формат Gemini `FunctionDeclaration` (name, description, parameters как JSON Schema).
   - При вызове инструмента: по `name` найти MCP tool, вызвать `session.call_tool`, вернуть результат в виде части сообщения для модели (function response).
3. Создать `agent/orchestrator.py` (или переименовать/расширить логику из текущего `ai_client.py`):
   - Вход: `user_message`, `chat_messages` (из Фазы 2), `mcp_client` (с подключённым сервером).
   - Получить инструменты: `mcp_client.get_tools()` → `mcp_tools_to_gemini_declarations(...)`.
   - Цикл:
     - Вызвать `GeminiClient.generate(chat_messages + [user_message], tools=declarations)`.
     - Если в ответе есть `function_calls`: для каждого вызова вызвать MCP `call_tool`, добавить в историю сообщение с результатом инструмента, повторить `generate` (без нового user message, только накопленная история).
     - Если в ответе только текст — вернуть его как финальный ответ.
   - Ограничить число итераций (например, 5–10), чтобы избежать бесконечного цикла.
4. В `interface/gui/worker.py` убрать `load_mcp_tools`, создание LangChain `AIClient`. Вместо этого вызывать новый оркестратор с `mcp_client` и историей из `AIClientService.load_memory_for_chat`.

**Результат:** ассистент отвечает с вызовом MCP-инструментов без LangChain и без langchain_mcp_adapters.

---

### Фаза 4: Удаление LangChain из кода и зависимостей

**Задачи:**

1. Удалить из кода все импорты и использование:
   - `langchain`, `langchain_google_genai`, `langchain_groq`, `langchain_mcp_adapters`, `langchain.memory`, `langchain.agents`, `langchain import hub`.
2. В `pyproject.toml` убрать: `langchain`, `langchain-google-genai`, `langchain-groq`, `langchain-mcp-adapters`. Добавить: `google-generativeai`.
3. Модуль `tools/code_interpreter.py` (если оставляем):
   - Заменить вызовы `ChatGoogleGenerativeAI` на `GeminiClient` из `core/llm_client.py`.
   - Убрать декоратор `@tool` LangChain; при необходимости описать инструмент вручную (например, для будущего MCP или своего формата).
4. Прогнать тесты и ручной сценарий: логин → новый чат → вопрос с веб-поиском (Tavily) → проверка ответа.

**Результат:** проект не зависит от LangChain, управление ИИ полностью в своём коде.

---

### Фаза 5 (опционально): улучшения

- **Стриминг:** если нужен посимвольный вывод в GUI — в `GeminiClient` использовать stream API Gemini и пробрасывать чанки в worker → view.
- **Ошибки и повторные попытки:** при падении вызова инструмента или LLM — ограниченное число retry и понятное сообщение пользователю.
- **Логирование:** логировать запросы/ответы LLM и вызовы инструментов (без секретов) для отладки.
- **Роль system:** добавить в начало истории системный промпт (например, «Ты ассистент. Используй инструменты при необходимости.») в формате, поддерживаемом Gemini.
- **Векторная long-term память (опционально):** хранить эмбеддинги сообщений или суммариев чатов (например, через ChromaDB, pgvector или in-memory); при сборке контекста помимо short-term окна подмешивать top-K релевантных фрагментов по семантическому поиску. Short-term при этом остаётся хронологическим окном из БД.

---

## Порядок выполнения (кратко)

1. **Фаза 1** — `core/llm_client.py` + Gemini SDK, вызов без инструментов.
2. **Фаза 2** — формат истории из БД, отказ от ConversationSummaryBufferMemory в `AIClientService`.
3. **Фаза 3** — адаптер MCP → Gemini, оркестратор с циклом tool call, замена логики в worker.
4. **Фаза 4** — удаление LangChain из кода и из `pyproject.toml`.
5. **Фаза 5** — по желанию (стриминг, retry, логи, system prompt).

---

## Зависимости после рефакторинга (ожидаемо)

- Оставить: `mcp[cli]`, `google-generativeai`, `pyside6`, `qasync`, `python-dotenv`, `bcrypt`, `async-timeout`, `tavily-python` (используется внутри MCP-сервера), при необходимости `docker`, `pydantic`.
- Удалить: `langchain`, `langchain-google-genai`, `langchain-groq`, `langchain-mcp-adapters` и все тянущиеся за ними пакеты.

После выполнения плана управление ИИ будет полностью в вашем коде: один клиент Gemini, своя сборка контекста из БД и явный цикл вызова MCP-инструментов.
