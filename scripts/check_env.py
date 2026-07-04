# -*- coding: utf-8 -*-
"""Bezpieczny podgląd konfiguracji: pokazuje, CZY zmienne są ustawione,
nigdy ich wartości. Uruchom po wypełnieniu .env:  py scripts/check_env.py
"""
import os
from common import load_env  # noqa: F401  (load_env odpala się przy imporcie)

VARS = [
    ("GOOGLE_API_KEY", True),
    ("RESEND_API_KEY", False),
    ("ALERT_RECIPIENTS", False),
    ("DASHBOARD_URL", False),
]

print("Konfiguracja (wartości ukryte):")
for name, required in VARS:
    val = os.environ.get(name, "")
    if val:
        # maska: nie pokazujemy wartości, tylko potwierdzenie i długość
        mark = "✅"
        info = f"ustawione (długość {len(val)})"
    else:
        mark = "❌ BRAK (wymagane)" if required else "- (opcjonalne, pominięte)"
        info = ""
    print(f"  {mark:24} {name} {info}")

if not os.environ.get("GOOGLE_API_KEY"):
    print("\nUzupełnij GOOGLE_API_KEY w pliku .env, aby pobrać realne dane.")
else:
    print("\nGOOGLE_API_KEY gotowy - można uruchomić: py scripts/collect.py")
