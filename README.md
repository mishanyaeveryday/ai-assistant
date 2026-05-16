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
- (Opcjonalnie) **`uv`** — [instrukcja instalacji](https://docs.astral.sh/uv/getting-started/installation/) lub klasycznie **`pip`**
- (Opcjonalnie) **Docker Desktop** — tylko jeśli będziesz używać sandboxa kodu (`DOCKER_CONTAINER`, patrz niżej). **Do samego GUI asystenta Docker nie jest wymagany.**

## Szybki start (krok po kroku)

Postępuj kolejno. Wszystkie komendy terminala zakładają, że jesteś w **katalogu `ai-assistant`** (tam, gdzie leży **`main.py`**). Inaczej MCP może nie znaleźć plików `mcp_tools/...`.

### 1. Przejdź do folderu projektu

```bash
cd ścieżka/do/repo/ai-assistant
```

### 2. Utwórz i włącz wirtualne środowisko (venv)

**macOS / Linux:**

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

**Windows:**

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\activate
```

Powinieneś zobaczyć prefiks **`(.venv)`** w wierszu poleceń.

### 3. Zainstaluj biblioteki Pythona

Z **aktywnym** `.venv`:

```bash
uv sync
```

Albo bez `uv`:

```bash
pip install -e .
```

### 4. Utwórz plik `.env` z kluczami API

```bash
cp example.env .env
```

Otwórz **`.env`** w edytorze i ustaw przynajmniej:

| Zmienna            | Opis                                                |
|--------------------|-----------------------------------------------------|
| `GENAI_API_KEY`    | klucz z [Google AI Studio](https://aistudio.google.com/apikey) |
| `TAVILY_API_KEY`   | klucz z [Tavily](https://tavily.com/) — **wymagany**, inaczej `config/settings.py` rzuci `ValueError` przy starcie |

`DOCKER_CONTAINER` zostaw puste lub uzupełnij dopiero po zbudowaniu obrazu Dockera — patrz **[Kontener Docker (sandbox kodu Python)](#kontener-docker-sandbox-kodu-python)** niżej w README.

### 5. (Opcja) Sandbox kodu w Dockerze

Konieczne **tylko** przy korzystaniu z **`DockerCodeInterpreter`**. Kroki są opisane w sekcji **„Kontener Docker (sandbox kodu Python)”** poniżej.

### 6. Uruchom aplikację

Nadal **`(.venv)`** aktywny, katalog **`ai-assistant`**:

```bash
python main.py
```

Powinno otworzyć się okno logowania. **Zarejestruj pierwsze konto** lub zaloguj się, utwórz czat i zacznij rozmowę.

### Tips / typowe problemy

- **`TAVILY_API_KEY is not set`** — sprawdź, czy plik `.env` jest naprawdę obok uruchamianego `main.py`, czy ma poprawny format `KLUCZ=wartość` (bez spacji wokół `=`).
- **MCP / ścieżki** — aplikacji nie uruchamiaj „z dowolnego katalogu”: zawsze `cd ai-assistant` przed `python main.py`, żeby relatywne ścieżki do `mcp_tools/...` działały.
- **`python` nie to 3.12** — sprawdź: `python --version` lub użyj `python3.12 main.py`.

---

Szczegóły techniczne (inne warianty venv/pip/docker) są w sekcjach **[Instalacja](#instalacja)** i **[Konfiguracja](#konfiguracja)** poniżej.

## Instalacja

### Środowisko wirtualne (venv)

Zalecane jest używanie **wirtualnego środowiska Pythona**, żeby zależności instalować obok projektu, a nie globalnie.

Z katalogu `ai-assistant`:

**macOS / Linux:**

```bash
cd ai-assistant
python3.12 -m venv .venv
source .venv/bin/activate
```

**Windows (PowerShell lub CMD):**

```powershell
cd ai-assistant
py -3.12 -m venv .venv
.\.venv\Scripts\activate
```

Po aktywacji w terminalu pojawi się zwykle prefiks **`(.venv)`**. Kolejne komendy `pip` lub `python` korzystają z tej instalacji.

**Uwaga:** środisko **`.venv`** nie powinno być commitowane (powinna być zasada w `.gitignore`).

Następnie z tego samego katalogu, **z aktywnym venv**, zrób instalację pakietów poniżej.

### Pakiety (uv lub pip)

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

### Plik `.env` i `example.env`

W projekcie jest szablon **`example.env`** (bezpieczny do commita — bez prawdziwych kluczy). Skopiuj go do **`.env`** w katalogu `ai-assistant` (tam, skąd uruchamiasz `python main.py`):

```bash
cd ai-assistant
cp example.env .env
```

Następnie edytuj **`.env`** i podstaw swoje wartości. Plik `.env` **nie powinien trafiać do repozytorium** — trzymaj w nim sekrety lokalnie.

Zawartość szablonu można opisać tak:

```env
# Wymagane — patrz wyjaśnienia niżej
GENAI_API_KEY=...
TAVILY_API_KEY=...

# Opcjonalne — nazwa lub tag obrazu Dockera dla sandboxa kodu (patrz „Kontener Docker”)
DOCKER_CONTAINER=...
```

- **GENAI_API_KEY** — [Google AI Studio](https://aistudio.google.com/apikey), model: `gemini-2.5-flash`
- **TAVILY_API_KEY** — [Tavily](https://tavily.com/) — zmienna jest wymagana przez `config/settings.py`; bez niej aplikacja nie wystartuje
- **DOCKER_CONTAINER** — nazwa lub tag obrazu używana przez **`DockerCodeInterpreter`** w `tools/code_interpreter.py` (opcja poza MCP i głównym GUI — tylko gdy korzystasz z tego narzędzia LangChain/Docker)

Dodatkowo opcjonalnie (np. inne eksperymentalne ścieżki w kodzie): **GROQ_API_KEY** — jeśli dany moduł z niego korzysta.

### Kontener Docker (sandbox kodu Python)

Pełna aplikacja z oknem **PySide6** nadal działa **bez Dockera**. Obraz **`Dockerfile`** w katalogu `ai-assistant` służy głównie jako **lekki środowiskowy sandbox** dla wykonywania wygenerowanego kodu w kontenerze (przez ustawienie **`DOCKER_CONTAINER`** i moduł `DockerCodeInterpreter`).

1. Zainstaluj i uruchom **Docker Desktop** lub demona Dockera.
2. Z katalogu `ai-assistant` zbuduj obraz:

```bash
cd ai-assistant
docker build -t ai-assistant-code-sandbox .
```

3. W pliku `.env` ustaw **taki sam tag**, np.:

```env
DOCKER_CONTAINER=ai-assistant-code-sandbox
```

4. W kodzie który wywołuje interpreter, **`DOCKER_CONTAINER` musi wskazywać na już zbudowany obraz** — inaczej `docker.containers.run(...)` się nie powiedzie.

Obraz kopiuje uproszczony `main.py` i instaluje pakiety wymienione w `Dockerfile`; katalog montowany z hosta przy uruchamianiu kontenera nadpisuje `/app`, ale biblioteki z obrazu pozostają dostępne do importów w uruchamianym skrypcie.

## Uruchomienie (skrót)

Pełny przepływ jest w **[Szybki start (krok po kroku)](#szybki-start-krok-po-kroku)**.

```bash
cd ai-assistant
source .venv/bin/activate   # macOS / Linux — na Windows: .\.venv\Scripts\activate
python main.py
```

Po starcie pojawia się logowanie; po zalogowaniu można tworzyć czaty i pisać do asystenta.

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

Z aktywnym środowiskiem wirtualnym:

```bash
cd ai-assistant
pytest tests/
```

## Licencja

Projekt własny.
