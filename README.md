# preza

Презентации в редактируемом PowerPoint для Codex и Claude Code. Начальная сессия ведёт работу, противоположный провайдер проверяет план через [claudex-loop](https://github.com/chaseai-yt/claudex-loop), изображения создаёт Codex с доступным imagegen. [PPT Master](https://github.com/hugohe3/ppt-master) собирает SVG в нативный PPTX. Речь в Word и анимация добавляются по запросу.

## Быстрый старт

Codex:

```sh
codex plugin marketplace add Inhibit0r/preza
codex plugin add preza@preza
```

Начните новую сессию, вызовите `$preza:setup`, затем `$preza:preza` с задачей.

Marketplace использует файлы своего выбранного checkout: `codex plugin marketplace add Inhibit0r/preza --ref <ветка-или-тег>` сохраняет выбранную версию и не переадресует установку плагина обратно на `main`.

Claude Code:

```sh
claude plugin marketplace add Inhibit0r/preza
claude plugin install preza@preza
```

В сессии выполните `/reload-plugins`, `/preza:setup`, затем `/preza:preza` с задачей. Навыки остаются ручными: политика Codex `allow_implicit_invocation: false` сохранена; Claude использует описание и настоящий Skill tool при его наличии.

На устройствах с управляемым переносимым стеком используйте его post-install обработчик вместо прямой установки.

## Начальное окружение

| Начальная сессия | Ведущий | Независимый рецензент | Генерация изображений |
|---|---|---|---|
| Codex | Codex | Claude CLI | встроенный imagegen, если доступен в сессии |
| Claude Code | Claude | Codex CLI | сессия Codex с imagegen |

Хост определяется по самой сессии и записывается в `runtime.json`; наличие двух CLI не задаёт ведущего. Скрипт распознаёт однозначный маркер `CODEX_THREAD_ID` / `CLAUDECODE`, при отсутствии или конфликте требует `--host`. Модели сохраняют настройки текущей среды; имена моделей одного клиента не подставляются в другой.

Файлы PPT Master ищутся в общей библиотеке `~/.agents/skills`, личных навыках клиентов и зарегистрированных пользовательских плагинах Claude. Codex читает их инструкцию по абсолютному пути; регистрация в Claude не означает доступность Skill tool в Codex. Копирование Markdown не переносит OAuth, MCP и нативные инструменты. Подробнее — [hosts.md](skills/preza/references/hosts.md).

## Зависимости

| Компонент | Назначение |
|---|---|
| Python 3.10+ | диагностика, сборка и проверка; Windows запускает с `-X utf8` |
| PPT Master и его `requirements.txt` | SVG → PPTX |
| claudex-loop и авторизованный CLI противоположного провайдера | независимое ревью |
| Microsoft PowerPoint на Windows или macOS | эталонный рендер |
| Poppler: `pdftoppm`, `pdffonts` | PDF → PNG, шрифты |
| сессия Codex с imagegen | изображения, когда они включены в оформление |

PPT Master можно установить как плагин Claude и использовать его зарегистрированные файлы из Codex:

```sh
claude plugin marketplace add hugohe3/ppt-master
claude plugin install ppt-master@ppt-master
python -X utf8 -m pip install --user -r <PPT_MASTER>/requirements.txt
python -X utf8 <PREZA>/skills/deck-house-rules/scripts/patch_ppt_master.py
```

На Mac используйте `python3`; ограничения установки Python-пакетов зависят от выбранной среды. Патчер меняет только управляемые указатели в трёх документах PPT Master. Guard, лицензия и спонсорская атрибуция сохраняются. После обновления любого из плагинов повторите setup.

Для отдельных блоков: Tavily/Firecrawl — внешние факты и поиск образцов; pandoc — материалы; frontend-slides — образцы; grill-me/grilling — идеи; доступный docx-навык, antiplagiat, avoid-ai-writing-russian и `aiw-ru` — речь. GitHub MCP нужен для репозиториев, но не является обязательным условием сборки презентации. Canva не требуется.

## Диагностика

```sh
python -X utf8 <PREZA>/skills/setup/scripts/doctor.py --host codex --offline --json
python -X utf8 <PREZA>/skills/setup/scripts/doctor.py --host claude --offline --json
```

Без `--offline` проверяются обновления зарегистрированных зависимостей. Код 0 — обязательные компоненты обнаружены и вход рецензента подтверждён; 1 — не хватает обязательного; 2 — не определён хост или ошибка конфигурации. Обнаруженный MCP ещё требует реального вызова в активной сессии; обнаруженная инструкция imagegen ещё не доказывает наличие инструмента.

## Маршрут

| Источник / запрос | Блоки |
|---|---|
| Внешний доклад | Факты → История → Облик → Сборка → Проверка |
| Файлы пользователя | Материалы → История → Облик → Сборка → Проверка |
| Идея | Идеи → История → Облик → Сборка → Проверка |
| Образцы | Референсы → нужный источник содержания → основной маршрут |
| Анимация | Движение между Обликом и Сборкой; `/preza:animate` / `$preza:animate` для готового проекта |
| Речь | Word по финальным слайдам |

Нерешённые содержательные выборы согласуются с пользователем; уже заданный бриф и разрешённые действия сохраняются. Контрольный прогон записывает технические решения отдельно и не выдаёт их за пользовательское принятие рабочей презентации. Роли, ход и доказательства сохраняются в `PLAN.md`.

House rules одинаковы на обоих хостах: план изображений проходит независимое ревью; картинки создаются через Codex imagegen; текст, графики и таблицы остаются редактируемыми; акценты делаются нативными фигурами без овальных свечений.

## Рендер и проверка

```sh
python -X utf8 <PREZA>/skills/preza/scripts/render_pptx.py <deck.pptx> <new-render-directory>
```

Windows: PowerPoint COM открывает отдельную копию с отключёнными макросами, экспортирует PDF, включает скрытые страницы только в копии и сохраняет исходный файл и уже открытые презентации. macOS: сохраняется прежний путь AppleScript через `render_pptx.sh`. Нужны локальный PowerPoint и Poppler; Linux не поддерживает эталонный рендер. Непустой каталог результата не перезаписывается.

После рендера осматриваются все страницы, сверяются шрифты и числа. Рендер показывает итоговые кадры, но не доказывает правильность воспроизведения анимации: её смотрят в PowerPoint. Проверки Windows и ролей покрыты тестами; живой прогон macOS выполняется на Mac.

## Проверки разработки

```sh
python -X utf8 -m unittest discover -s tests -v
python -X utf8 skills/setup/scripts/doctor.py --selftest
python -X utf8 skills/deck-house-rules/scripts/patch_ppt_master.py --selftest
```

Тесты проверяют исходное окружение, симметричные роли, приоритет локальных адаптаций, изоляцию MCP текущего клиента и защиту файлов рендера. Полный контрольный маршрут дополнительно требует реальных CLI, imagegen, PPT Master и PowerPoint.

## Участие и лицензия

Ошибки — [issues](https://github.com/Inhibit0r/preza/issues), изменения — pull request. [MIT](LICENSE); зависимости распространяются по своим лицензиям.
