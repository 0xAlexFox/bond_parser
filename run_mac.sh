#!/usr/bin/env bash
set -euo pipefail

# перейти в папку скрипта
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# выбрать интерпретатор
if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo "Python не найден. Установите python3 и повторите." >&2
  exit 1
fi

# создать venv при необходимости
if [ ! -d "venv" ]; then
  "$PY" -m venv venv
fi

# активировать venv
# shellcheck disable=SC1091
source "venv/bin/activate"

# обновить pip и поставить зависимости
python -m pip install --upgrade pip
pip install -r requirements.txt

# проверить наличие токена
if [ ! -f "config.env" ]; then
  echo "Файл config.env не найден. Создайте его и положите в него TINKOFF_INVEST_TOKEN." >&2
  echo 'Пример: TINKOFF_INVEST_TOKEN="t.XXXXXXXXXXXXXXXXXXXXXXXX"' >&2
  exit 1
fi

# запуск основной команды
python run.py