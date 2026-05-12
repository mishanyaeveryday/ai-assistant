# Plan projektu — Agent AI z MCP

## Cel projektu
Desktop agent AI (PyQt) z wbudowanymi narzędziami MCP oraz możliwością dodawania własnych serwerów MCP przez użytkownika.

---

## Architektura warstwy narzędzi

```
┌─────────────────────────────────────┐
│           Interfejs użytkownika      │
│              (PyQt)                 │
└────────────────┬────────────────────┘
                 │
┌────────────────▼────────────────────┐
│         Agent (Planner + Executor)  │
│           + LiteLLM                 │
└──────┬──────────────────┬───────────┘
       │                  │
┌──────▼──────┐    ┌──────▼──────────┐
│  Wbudowane  │    │  Użytkownika    │
│  MCP serwery│    │  MCP serwery    │
│  (zawsze)   │    │  (dodawane)     │
└─────────────┘    └─────────────────┘
```

---

## Wbudowane MCP serwery (stock)

### Obowiązkowe
- **Terminal** — wykonywanie poleceń systemowych (bash/cmd)
- **Filesystem** — czytanie, zapis, tworzenie, usuwanie plików
- **Code Runner** — uruchamianie kodu Python/bash, generowanie wykresów itp.
- **Web Search** — podstawowe wyszukiwanie w internecie
- **Screenshot** — zrzut ekranu (kluczowe dla sterowania aplikacjami — główny temat dyplomu)

---

## Użytkownik dodaje własne MCP serwery

Przykłady które użytkownik może dodać sam:
- Gmail / Outlook (pisanie i wysyłanie maili)
- Google Drive / Notion (zarządzanie dokumentami)
- GitHub (operacje na repozytoriach)
- Slack / Discord (komunikacja)
- Bazy danych (PostgreSQL, SQLite)
- Dowolny inny serwer MCP zgodny ze standardem

### Jak użytkownik dodaje serwer (dwa sposoby do wyboru)

**Opcja A — przez UI (formularz w aplikacji):**
```
Nazwa serwera:  [ GitHub MCP        ]
Komenda:        [ npx @modelcp/github]
Argumenty:      [ --token xyz       ]
[ Dodaj serwer ]
```

**Opcja B — przez plik konfiguracyjny:**
```json
{
  "mcp_servers": {
    "github": {
      "command": "npx",
      "args": ["@modelcp/github"],
      "env": {
        "GITHUB_TOKEN": "..."
      }
    },
    "gmail": {
      "command": "python",
      "args": ["servers/gmail_server.py"]
    }
  }
}
```

---

## Implementacja techniczna

### Stack
- **UI** — PyQt (+ QSS style dla nowoczesnego wyglądu)
- **LLM** — LiteLLM (jeden interfejs → Gemini / GPT / Claude / OpenRouter)
- **MCP** — własna implementacja klienta MCP (stdio transport)
- **Konfiguracja** — plik JSON (mcp_config.json)

### Struktura projektu (propozycja)
```
agent/
├── main.py                  # Start aplikacji PyQt
├── core/
│   ├── planner.py           # Moduł Planner (LLM reasoning)
│   ├── executor.py          # Moduł Executor (wywołanie narzędzi)
│   └── mcp_client.py        # Klient MCP (obsługa połączeń)
├── servers/                 # Wbudowane serwery MCP
│   ├── terminal_server.py
│   ├── filesystem_server.py
│   ├── code_runner_server.py
│   ├── search_server.py
│   └── screenshot_server.py
├── ui/
│   ├── main_window.py
│   ├── chat_widget.py
│   └── settings_widget.py   # UI do zarządzania serwerami
├── mcp_config.json          # Konfiguracja użytkownika
└── requirements.txt
```

---

## Powiązanie z wymaganiami dyplomu

| Wymaganie | Realizacja |
|-----------|------------|
| WF2 — Tool Calling | Wbudowane + użytkownika MCP serwery |
| WN3 — Modułowość | Dynamiczne dodawanie serwerów przez config/UI |
| WN1 — Human-in-the-loop | Potwierdzenie przed akcjami krytycznymi (terminal) |
| Rozdział 5.5 — Testy modeli | LiteLLM → łatwa zmiana modelu jedną linią |

---

## TODO (kolejność pracy)

- [ ] Dokończyć wbudowane serwery MCP (terminal, filesystem, code runner)
- [ ] Zaimplementować klienta MCP (stdio)
- [ ] Podłączyć LiteLLM zamiast bezpośredniego Gemini API
- [ ] Dodać UI do zarządzania serwerami użytkownika (settings)
- [ ] Poprawić wygląd PyQt przez QSS style
- [ ] Przetestować z różnymi modelami (rozdział 5.5)
- [ ] Napisać rozdziały 3+4 na podstawie gotowego kodu