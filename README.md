MOEX/Tinkoff Bonds Export — README

Экспорт облигаций в Excel с данными из MOEX ISS и Tinkoff Invest API:
	•	цена, доходность к погашению (YTM), НКД, купонная ставка/частота/размер, номинал;
	•	дата погашения, «грубая» дюрация (годы до погашения);
	•	«следующая дата купона» (из Tinkoff API);
	•	фильтры по YTM и дюрации;
	•	запуск одной командой на Windows/macOS.

⸻

Содержание
	•	Структура проекта
	•	Что такое «базовые инструменты»
	•	Установка
	•	Быстрый запуск
	•	Настройка
	•	config.env — токен
	•	params.yaml — параметры выгрузки
	•	Скрипты запуска
	•	macOS / Linux
	•	Windows
	•	«Чистый» запуск (пересборка окружения)
	•	Колонки в Excel
	•	Примеры
	•	Диагностика MOEX (опционально)
	•	FAQ / Ошибки и решения
	•	Замечания по данным

⸻

Структура проекта

invest/
├─ README.md
├─ requirements.txt           # зависимости (pip)
├─ config.env                 # токен (не коммитить!)
├─ params.yaml                # параметры выгрузки/фильтры
├─ run.py                     # единая точка входа
├─ tbank_bonds_to_excel.py    # основная логика
├─ moex_ytm_probe.py          # диагностика MOEX ISS (опционально)
├─ run_mac.sh                 # запуск для macOS/Linux
├─ run_clean_mac.sh           # «чистый» запуск для macOS/Linux
├─ run_windows.bat            # запуск для Windows
└─ run_clean_windows.bat      # «чистый» запуск для Windows


⸻

Что такое «базовые инструменты»

В Tinkoff API у справочника облигаций есть два статуса:
	•	INSTRUMENT_STATUS_BASE — «базовые» бумаги: ликвидные и актуально торгуемые;
	•	INSTRUMENT_STATUS_ALL — весь каталог, включая архивные/делистинг/технические.

В params.yaml:
	•	all: false → берём только базовые (рекомендовано для обычной работы);
	•	all: true → берём всё (полный справочник).

⸻

Установка
	1.	Установите Python 3.10+ (рекомендовано 3.11–3.13).
	2.	Склонируйте/распакуйте проект в папку invest/.
	3.	Убедитесь, что у вас есть интернет-доступ к iss.moex.com и invest-public-api.tinkoff.ru.

⸻

Быстрый запуск

macOS / Linux

cd invest
chmod +x run_mac.sh run_clean_mac.sh
./run_mac.sh

Windows

Откройте invest\run_windows.bat (двойной клик)
или из cmd:

cd invest
run_windows.bat

При первом запуске будет создано виртуальное окружение venv, установлены зависимости и запущен экспорт с параметрами из params.yaml.

⸻

Настройка

config.env — токен

Создайте файл config.env в корне проекта:

TINKOFF_INVEST_TOKEN="t.XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"

	•	Токен берётся в личном кабинете Tinkoff Инвестиций (API v2).
	•	Файл держите вне Git (не коммитьте публично).

params.yaml — параметры выгрузки

# Имя выходного Excel
outfile: "bonds_today.xlsx"

# true — весь справочник; false — только базовые
all: false

# Фильтры (можно null)
min_ytm: 12.0        # минимальная YTM, % годовых (например 12.0)
max_duration: 3.0    # максимальные годы до погашения (грубая дюрация)

# Список ISIN; если задан — берём только эти бумаги
only_isins:
  - "RU000A10B4T4"
  - "RU000A105GE2"
  - "RU000A0ZYR91"
  - "RU000A0ZYX28"

Если only_isins пуст, экспорт идёт по всему справочнику (с учётом all и фильтров).

⸻

Скрипты запуска

macOS / Linux
	•	Обычный запуск:

./run_mac.sh


	•	«Чистый» запуск (полностью пересобрать окружение):

./run_clean_mac.sh



Windows
	•	Обычный запуск:

run_windows.bat


	•	«Чистый» запуск:

run_clean_windows.bat



«Чистый» запуск (пересборка окружения)

Используйте, если:
	•	после обновления Python/пакетов появились ошибки импортов;
	•	конфликт версий зависимостей;
	•	«сломались» бинарные колёса (grpc/aiohttp/pandas) или SSL;
	•	переносите проект на новую машину и хотите гарантированную чистую установку.

Скрипт удалит venv, создаст заново, поставит зависимости и запустит экспорт.

⸻

Колонки в Excel
	•	ISIN
	•	Эмитент (короткое имя с MOEX; при отсутствии — из Tinkoff)
	•	Текущая цена (MOEX marketdata.LAST или history.LEGALCLOSEPRICE)
	•	НКД (MOEX marketdata.ACCRUEDINT, фолбэк — securities.ACCRUEDINT)
	•	Купонная ставка, % (MOEX securities.COUPONPERCENT)
	•	Размер купона (денег) (MOEX securities.COUPONVALUE)
	•	Частота купонов (в год) ≈ round(365 / COUPONPERIOD)
	•	Номинал (MOEX securities.FACEVALUE)
	•	Следующая дата купона (из Tinkoff API get_bond_coupons; ближайшая будущая)
	•	Дата погашения (Tinkoff; при пустой — MOEX MATDATE, кроме 0000-00-00)
	•	Дюрация, лет (грубо) — годы до погашения (по календарю)
	•	Доходность к погашению (MOEX, % годовых)
(MOEX marketdata.YIELD; если пусто — берётся самый свежий history.YIELDCLOSE за 365 дней)
	•	Тип купона (плавающий/фиксированный — Tinkoff)
	•	Амортизация (да/нет — Tinkoff)
	•	Рейтинг — инвертированное отображение: LOW↔HIGH (по запросу)

⸻

Примеры
	1.	Обычный экспорт «базовых» облигаций:
	•	macOS:

./run_mac.sh


	•	Windows:

run_windows.bat


	2.	Фильтры: YTM ≥ 14% и дюрация ≤ 3 лет
Отредактируйте params.yaml:

min_ytm: 14.0
max_duration: 3.0

И снова запустите сценарий.

	3.	Только определённые ISIN:

only_isins:
  - "RU000A10B4T4"
  - "RU000A105GE2"

all и фильтры применятся к этим бумагам.

⸻

Диагностика MOEX (опционально)

Быстро проверить доступность данных по ISIN:

python moex_ytm_probe.py RU000A10B4T4 RU000A105GE2

Выведет: SECID / SHORTNAME / MATDATE / BOARD / LAST / YTM.
Полезно, если YTM/цена пустые — можно понять, что именно отдаёт MOEX ISS.

⸻

FAQ / Ошибки и решения

1) Could not find a version that satisfies the requirement tinkoff-investments>=...
Используйте версию из requirements.txt проекта:

tinkoff-investments==0.2.0b116

Если случайно опечатались (например, inkoff-...), поправьте и выполните «чистый» запуск.

2) SSL: certificate verify failed, self-signed certificate in certificate chain
На macOS это бывает. В проекте используется certifi и явный SSL-контекст для aiohttp.
Если всё равно воспроизводится — проверьте прокси/антивирус/VPN, смените DNS на 1.1.1.1 или 8.8.8.8.

3) Пустая YTM/цена
MOEX может не отдавать marketdata.YIELD (нет сделок) — скрипт берёт history.YIELDCLOSE за 365 дней.
Если и там пусто — вероятно, инструмент не торговался; проверьте moex_ytm_probe.py.

4) «Следующая дата купона» пустая
Иногда Tinkoff API не возвращает событий — поле останется пустым. Можно добавить фолбэк через MOEX (по запросу).

5) ModuleNotFoundError / ImportError после обновлений
Сделайте «чистый» запуск: пересоберите venv через run_clean_mac.sh / run_clean_windows.bat.

⸻

Замечания по данным
	•	Значения YTM — официальные расчёты MOEX (marketdata/history).
	•	Цена/НКД — из MOEX; привязаны к выбранной доске (обычно TQCB).
	•	Дюрация (грубо) — это не Macaulay/Modified, а простые годы до погашения.
Если нужна точная дюрация/конвексность — можно добавить расчёт по денежному потоку (скажи — подготовлю).

⸻

Готово! Дальше вам достаточно:
	1.	заполнить config.env токеном,
	2.	при необходимости настроить params.yaml,
	3.	запустить run_mac.sh (или run_windows.bat).# bond_parser
