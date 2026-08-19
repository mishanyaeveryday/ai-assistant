# AI Assistant

Desktopowa aplikacja z graficznym interfejsem (PySide6), umożliwiająca rozmowę z asystentem AI z obsługą narzędzi (MCP) i zapisem historii czatów.

## Możliwości

- **Rejestracja i logowanie** — konta użytkowników, hasła hashowane (bcrypt)
- **Wiele czatów** — tworzenie czatów, przełączanie między nimi, historia wiadomości
- **Asystent AI** — odpowiedzi generowane przez model Gemini (LangChain), z pamięcią kontekstu w obrębie czatu
- **Narzędzia MCP** — wyszukiwanie w internecie (Tavily), operacje na plikach, terminal, zrzuty ekranu, sterowanie myszą/klawiaturą oraz **sandbox kodu Python w Dockerze** — wszystko przez serwery MCP
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

Konieczne **tylko** jeśli chcesz, żeby asystent mógł uruchamiać kod Python narzędziem **`run_python_code`**. Kroki są opisane w sekcji **„Kontener Docker (sandbox kodu Python)”** poniżej.

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
- **DOCKER_CONTAINER** — nazwa/tag zbudowanego obrazu Dockera, którego używa narzędzie MCP **`run_python_code`** (`mcp_tools/code_interpreter/server.py`) do uruchamiania kodu Python w sandboxie. Bez tej zmiennej narzędzie jest zarejestrowane w GUI, ale przy próbie użycia zwróci błąd — patrz **[Kontener Docker (sandbox kodu Python)](#kontener-docker-sandbox-kodu-python)**

Dodatkowo opcjonalnie (np. inne eksperymentalne ścieżki w kodzie): **GROQ_API_KEY** — jeśli dany moduł z niego korzysta.

### Kontener Docker (sandbox kodu Python)

Pełna aplikacja z oknem **PySide6** nadal działa **bez Dockera**. Kontener jest potrzebny tylko do narzędzia MCP **`run_python_code`** (`mcp_tools/code_interpreter/server.py`), które pozwala asystentowi uruchamiać kod Python w izolowanym, jednorazowym sandboxie. Bez skonfigurowanego Dockera reszta aplikacji (GUI, czaty, pozostałe narzędzia MCP) działa normalnie — to narzędzie po prostu zwróci błąd, jeśli zostanie użyte.

#### 1. Uruchom Docker

Zainstaluj i uruchom **Docker Desktop** (macOS/Windows) lub demona `dockerd` (Linux). Sprawdź, że działa:

```bash
docker info
```

#### 2. Zbuduj obraz sandboxa

Z katalogu `ai-assistant` (tam, gdzie jest `Dockerfile`):

```bash
cd ai-assistant
docker build -t ai-assistant-code-sandbox .
```

Obraz bazuje na `python:3.11.10-slim-bookworm` i instaluje z góry biblioteki wymienione w `Dockerfile` (m.in. `pandas`, `numpy`, `matplotlib`, `plotly`, `python-docx`, `beautifulsoup4`, `requests`), żeby kod generowany przez asystenta miał je od razu dostępne bez instalowania w locie.

#### 3. Ustaw `DOCKER_CONTAINER` w `.env`

W pliku `.env` (w katalogu `ai-assistant`) wpisz **dokładnie ten sam tag**, którego użyłeś przy `docker build -t ...`:

```env
DOCKER_CONTAINER=ai-assistant-code-sandbox
```

Jeśli zmienna jest pusta albo obraz o tym tagu nie istnieje, `run_python_code` zwróci komunikat błędu zamiast wykonać kod — reszta aplikacji nie jest tym blokowana.

#### 4. Uruchom aplikację normalnie

```bash
python main.py
```

`main.py` przy starcie łączy się m.in. z `mcp_tools/code_interpreter/server.py` (patrz `setup_mcp` w `main.py`) — narzędzie `run_python_code` jest wtedy dostępne dla asystenta, o ile Docker działa i obraz jest zbudowany.

#### Jak działa sandbox (kod nigdzie nie jest zapisywany na stałe)

Za każdym wywołaniem `run_python_code`:

1. Kod dostarczony przez asystenta jest zapisywany do **tymczasowego katalogu** (`tempfile.TemporaryDirectory`), tworzonego na czas jednego uruchomienia.
2. Ten katalog jest montowany do kontenera jako `/sandbox`, a kontener uruchamia `python /sandbox/main.py`.
3. Po zakończeniu wykonania kontener jest usuwany (`remove=True`), a tymczasowy katalog na hoście jest kasowany automatycznie po wyjściu z bloku `with` — **sam kod nie zostaje zapisany nigdzie na stałe w repo ani na dysku**.
4. Dodatkowo katalog z **`WORKSPACE_DIR`** (patrz zmienna w `.env`, domyślnie `~/ai-assistant-workspace`) jest montowany do kontenera jako `/workspace`. Jeśli kod ma wygenerować plik, który ma **przetrwać** po zakończeniu (raport, wykres, wygenerowane dane), powinien zapisać go pod ścieżką `/workspace/...` wewnątrz kontenera — wtedy plik ląduje trwale w `WORKSPACE_DIR` na hoście. Wszystko zapisane gdzie indziej (np. w bieżącym katalogu `/sandbox`) jest traktowane jako dane tymczasowe i znika razem z kontenerem.

Uwaga: to inny mechanizm niż starszy `tools/code_interpreter.py` / `DockerCodeInterpreter`, który zapisywał wykonywany skrypt na stałe do katalogu `tools/files/` na hoście. `tools/code_interpreter.py` jest zachowany w repo (ma własne testy), ale **nie jest** podpięty do `main.py` / GUI — aktualnym, używanym w aplikacji narzędziem jest `mcp_tools/code_interpreter/server.py`.

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
│   ├── web_search/          # serwer MCP z narzędziem Tavily
│   ├── filesystem_command/  # odczyt/zapis plików w WORKSPACE_DIR
│   ├── terminal_command/    # wykonywanie poleceń shell
│   ├── screenshot_command/  # zrzuty ekranu
│   ├── input_control/       # sterowanie myszą/klawiaturą
│   └── code_interpreter/    # sandbox kodu Python w Dockerze (run_python_code)
├── tools/                  # starszy, niepodpięty do GUI code_interpreter (LangChain + Docker)
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
