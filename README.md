# preza

Презентации в PowerPoint под ключ для Claude Code. Вы описываете задачу, preza собирает под неё маршрут из блоков — факты, ваши материалы или идеи, разбор образцов, история, облик, сборка, проверка — и выдаёт нативный PPTX через [ppt-master](https://github.com/hugohe3/ppt-master). Графики и таблицы в нём — объекты PowerPoint, текст редактируется. Codex проверяет план и рисует иллюстрации. По желанию — речь по слайдам в Word.

## Быстрый старт

В сессии Claude Code:

```
/plugin marketplace add Inhibit0r/preza
/plugin install preza@preza
/reload-plugins
/preza:setup
```

`/preza:setup` покажет, чего не хватает, и предложит поставить. Затем:

```
/preza:preza доклад на 6 минут: ценовая политика и вертикальная интеграция компании X
```

preza задаст до четырёх вопросов, покажет маршрут и остановится для вашего решения на раскадровке, выборе облика и финале.

## Что нужно

| Компонент | Зачем | Нужен |
|---|---|---|
| Claude Code | ведущий: план, текст, сборка | всегда |
| [ppt-master](https://github.com/hugohe3/ppt-master) + его Python-пакеты | SVG → нативный PPTX | всегда |
| [claudex-loop](https://github.com/chaseai-yt/claudex-loop) | ревью плана и картинок в Codex | всегда |
| Codex CLI, вход по подписке ChatGPT | ревью, иллюстрации через `$imagegen` | всегда |
| Microsoft PowerPoint (macOS) | эталонный рендер слайдов для проверки | всегда |
| poppler | PDF → PNG, проверка шрифтов | всегда |
| Tavily и Firecrawl MCP | поиск | блоки «Факты», «Референсы» |
| [frontend-slides](https://github.com/zarazhangrui/frontend-slides) | разбор образцов PPTX, дизайн-шаблоны | «Референсы» |
| document-skills (docx) из [anthropics/skills](https://github.com/anthropics/skills) | речь в Word | «Речь» |
| [avoid-ai-writing-russian](https://github.com/ormeilu/avoid-ai-writing-russian) и детектор `aiw-ru` | проверка речи на приметы ИИ-текста | «Речь» |
| [mattpocock-skills](https://github.com/mattpocock/skills) (`grill-me`) | интервью по вашим идеям | «Идеи» |
| [to-md](https://github.com/Inhibit0r/to-md) или pandoc | чтение ваших файлов | «Материалы» |

## Установка

Точные команды с путями для вашей машины выдаёт `/preza:setup`. Ниже — то же вручную.

### Claude Code — ведущий

```bash
claude plugin marketplace add Inhibit0r/preza
claude plugin install preza@preza

claude plugin marketplace add hugohe3/ppt-master
claude plugin install ppt-master@ppt-master
claude plugin marketplace add chaseai-yt/claudex-loop
claude plugin install claudex-loop@claudex-loop
```

Python-пакеты ppt-master и правила оформления preza внутри ppt-master:

```bash
python3 -m pip install --user -r <папка ppt-master>/requirements.txt   # Homebrew Python: добавьте --break-system-packages
python3 <папка preza>/skills/deck-house-rules/scripts/patch_ppt_master.py
```

Необязательное — нужно только своим блокам:

```bash
claude plugin marketplace add zarazhangrui/frontend-slides && claude plugin install frontend-slides@frontend-slides
claude plugin marketplace add anthropics/skills && claude plugin install document-skills@anthropic-agent-skills
claude plugin marketplace add ormeilu/avoid-ai-writing-russian && claude plugin install avoid-ai-writing-russian@avoid-ai-writing-russian
uv tool install aiw-ru
claude plugin install mattpocock-skills
claude plugin marketplace add Inhibit0r/to-md && claude plugin install to-md@to-md

# поиск; ключи — в переменных TAVILY_API_KEY и FIRECRAWL_API_KEY профиля оболочки
claude mcp add -s user -t http tavily https://mcp.tavily.com/mcp -H 'Authorization: Bearer ${TAVILY_API_KEY}'
claude mcp add -s user -t http firecrawl https://mcp.firecrawl.dev/v2/mcp -H 'Authorization: Bearer ${FIRECRAWL_API_KEY}'
```

После установки плагинов — `/reload-plugins` в сессии.

### Codex CLI — напарник

```bash
npm install -g @openai/codex
codex login
```

`$imagegen` встроен в Codex, отдельный ключ для картинок не нужен. Генерация расходует лимит подписки ChatGPT.

Навыки preza можно поставить и в Codex: `codex plugin marketplace add Inhibit0r/preza`, затем `codex plugin add preza@preza`. Ведущим в Codex preza не проверялся — ppt-master ставится как плагин Claude Code.

### Система (macOS)

```bash
brew install poppler
```

Microsoft PowerPoint (Office 2021 или Microsoft 365) откройте один раз. При первом рендере macOS спросит разрешение управлять PowerPoint — разрешите.

## Проверка окружения

`/preza:setup` запускает `skills/setup/scripts/doctor.py`: проверяет ядро и компоненты блоков, сравнивает установленные плагины с их репозиториями и предлагает установить или обновить недостающее. Из терминала:

```bash
python3 skills/setup/scripts/doctor.py            # таблица и команды
python3 skills/setup/scripts/doctor.py --offline  # без проверки обновлений
python3 skills/setup/scripts/doctor.py --json
```

Код выхода 1 — не хватает обязательного.

## Как пользоваться

| Запрос | Маршрут |
|---|---|
| `/preza:preza доклад на 6 минут: структура рынка и ценовая политика компании X` | Факты → История → Облик → Сборка → Проверка |
| `/preza:preza внутренняя презентация для команды про мою идею, 10 минут, черновик` | Идеи → История → Облик → Сборка → лёгкая проверка |
| `/preza:preza в refs/ три презентации — разбери приёмы и сделай свою про итоги квартала по report.xlsx, для руководства` | Референсы → Материалы → История → Облик → Сборка → полная проверка |

Облик каждой презентации выводится из её темы: шаблоны ppt-master служат библиотекой приёмов, фоны и иллюстрации рисует Codex. Порядок работы — в [skills/preza/SKILL.md](skills/preza/SKILL.md), блоки — в [skills/preza/blocks](skills/preza/blocks).

## Ограничения

- Рендер для проверки идёт через PowerPoint на macOS (AppleScript). На Windows сборка работает, рендер — вручную: PowerPoint → «Сохранить как» PDF → `pdftoppm -png -r 96`.
- После `claude plugin update ppt-master@ppt-master` запустите `/preza:setup` — он вернёт правила оформления в ppt-master.

## Участие

Ошибки и предложения — в [issues](https://github.com/Inhibit0r/preza/issues), правки — pull request'ом.

## Лицензия

[MIT](LICENSE). Зависимости распространяются под лицензиями своих авторов.
