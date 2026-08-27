.PHONY: notify

# 사용법: make notify STOCK="알파벳A"
STOCK ?= 알파벳A

notify:
	uv run python notify_telegram_analysis.py "$(STOCK)"
