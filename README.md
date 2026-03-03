# AI Assistant

Desktopowa aplikacja z graficznym interfejsem (PySide6), umożliwiająca rozmowę z asystentem AI z obsługą narzędzi (MCP) i zapisem historii czatów.

## Możliwości

- **Rejestracja i logowanie** — konta użytkowników, hasła hashowane (bcrypt)
- **Wiele czatów** — tworzenie czatów, przełączanie między nimi, historia wiadomości
- **Asystent AI** — odpowiedzi generowane przez model Gemini (LangChain), z pamięcią kontekstu w obrębie czatu
- **Narzędzia MCP** — wyszukiwanie w internecie (Tavily) przez serwer MCP
- **Baza SQLite** — użytkownicy, czaty i historia wiadomości przechowywane lokalnie

## Wymagania

- Python 3.12+
- Konto i klucze API: Google AI (Gemini), Tavily

## Instalacja

Z katalogu `ai-assistant`:

```bash
# z uv
uv sync

# lub z pip
pip install -e .
```

Zależności deweloperskie (pytest):

```bash
pip install -e ".[dev]"
```

## Konfiguracja

Utwórz plik `.env` w katalogu `ai-assistant` (obok `main.py`):

```env
# Wymagane
GENAI_API_KEY=twój_klucz_google_ai
TAVILY_API_KEY=twój_klucz_tavily

# Opcjonalne (używane przy interpreterze kodu w Dockerze)
GROQ_API_KEY=...
DOCKER_CONTAINER=python:3.11-slim
```

- **GENAI_API_KEY** — [Google AI Studio](https://aistudio.google.com/apikey), model: `gemini-2.5-flash`
- **TAVILY_API_KEY** — [Tavily](https://tavily.com/) — bez tego aplikacja nie wystartuje
- **DOCKER_CONTAINER** — obraz Dockera do wykonywania kodu (jeśli korzystasz z interpretera kodu)

## Uruchomienie

Uruchamiaj z katalogu `ai-assistant`, żeby ścieżki do serwera MCP były poprawne:

```bash
cd ai-assistant
python main.py
```

Po starcie pojawi się okno logowania. Po zalogowaniu możesz tworzyć czaty i pisać wiadomości do asystenta.

## Struktura projektu

```
ai-assistant/
├── main.py                 # punkt wejścia, inicjalizacja GUI i MCP
├── config/
│   └── settings.py         # zmienne z .env, modele
├── core/
│   ├── models.py           # User, Chat, MessageHistory
│   └── services.py         # AuthService, ChatService, MessageService, AIClientService
├── db/
│   └── database.py         # SQLite: użytkownicy, czaty, wiadomości
├── agent/
│   ├── ai_client.py        # LangChain agent (Gemini) + narzędzia
│   └── mcp_client.py       # połączenie z serwerem MCP
├── interface/
│   └── gui/                # PySide6: okna, kontrolery, worker AI
├── mcp_tools/
│   └── web_search/         # serwer MCP z narzędziem Tavily
├── tools/                  # code_interpreter (Docker) — opcjonalnie
└── tests/
```

## Testy

```bash
cd ai-assistant
pytest tests/
```

## Licencja

Projekt własny.
