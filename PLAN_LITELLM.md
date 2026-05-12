# Plan migracji na LiteLLM (skrót)

## Cel
Jednolity dostęp do wielu modeli (Gemini, OpenAI, Anthropic itd.) zamiast bezpośredniego SDK Gemini, przy zachowaniu pętli wywołań narzędzi MCP.

## Kroki

1. **Integracja** — dodać zależność `litellm`; wybrać tryb: biblioteka w procesie aplikacji (`litellm.acompletion`) lub opcjonalnie osobny LiteLLM Proxy + klient OpenAI.

2. **Konfiguracja** — w `.env` / `settings`: klucze API zgodne z dokumentacją LiteLLM dla wybranych providerów; jedna zmienna z nazwą modelu (np. `gemini/gemini-2.5-flash`).

3. **Warstwa LLM** — jeden moduł (np. zamiast `GeminiClient`): wejście `messages` w formacie OpenAI (`system` / `user` / `assistant` / `tool`), opcjonalnie `tools`, `temperature`; wyjście: tekst końcowy lub lista `tool_calls` do obsługi w orkiestratorze.

4. **Historia czatu** — funkcja mapująca pamięć z bazy (`input` / `output`) na listę wiadomości OpenAI; systemowy prompt jako `role: "system"`.

5. **Narzędzia MCP** — konwersja schematu MCP na format OpenAI: `tools=[{"type":"function","function":{"name","description","parameters"}}]` (parametry = `inputSchema`).

6. **Orkiestrator** — pętla: wywołanie LLM → jeśli są `tool_calls`, wykonanie `call_tool` → dopisanie wiadomości `assistant` (z `tool_calls`) i `tool` (z `tool_call_id`) → ponowne wywołanie; limit iteracji (np. 5); zwrot ostatniego tekstu bez wywołań narzędzi.

7. **Testy ręczne** — rozmowa bez narzędzi; rozmowa z narzędziem MCP (wielokrotne rundy); opcjonalnie zmiana modelu na innego providera.

8. **Porządki** — usunąć nieużywane importy i pakiety (`google-genai` / `google-generativeai`, LangChain od Gemini, jeśli niepotrzebne); zsynchronizować `README` z nowymi zmiennymi środowiskowymi.

## Pliki do zmiany (orientacyjnie)
`core/llm_client.py`, `agent/orchestrator.py`, `agent/tools_adapter.py`, `config/settings.py`.
