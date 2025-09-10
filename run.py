#!/usr/bin/env python3
import os
import sys
import yaml
import asyncio

from tbank_bonds_to_excel import export_bonds  # наша асинхронная функция

def load_env_token(env_path: str = "config.env") -> str:
    token = None
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as fh:
            for ln in fh:
                s = ln.strip()
                if not s or s.startswith("#"):
                    continue
                if s.startswith("TINKOFF_INVEST_TOKEN"):
                    # поддержка форматов: KEY=value, KEY="value"
                    parts = s.split("=", 1)
                    if len(parts) == 2:
                        token = parts[1].strip().strip('"').strip("'")
                        break
    if not token:
        token = os.getenv("TINKOFF_INVEST_TOKEN")
    if not token:
        raise SystemExit("Не найден TINKOFF_INVEST_TOKEN ни в config.env, ни в переменных окружения.")
    return token

def load_params(path: str = "params.yaml") -> dict:
    if not os.path.exists(path):
        # параметры по умолчанию
        return {
            "outfile": "bonds_today.xlsx",
            "all": False,
            "min_ytm": None,
            "max_duration": None,
            "only_isins": [],
        }
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    data.setdefault("outfile", "bonds_today.xlsx")
    data.setdefault("all", False)
    data.setdefault("min_ytm", None)
    data.setdefault("max_duration", None)
    data.setdefault("only_isins", [])
    return data

def main():
    token = load_env_token()
    params = load_params()
    asyncio.run(export_bonds(
        token=token,
        outfile=params["outfile"],
        only_isins=params.get("only_isins") or None,
        base_only=not bool(params.get("all")),
        min_ytm=params.get("min_ytm"),
        max_duration=params.get("max_duration"),
    ))

if __name__ == "__main__":
    main()