#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Проверка дубликатов в cartridge_database.json
"""
import json
from pathlib import Path
from difflib import SequenceMatcher

data_file = Path("data/cartridge_database.json")

with open(data_file, 'r', encoding='utf-8') as f:
    data = json.load(f)

print("=" * 80)
print("ПРОВЕРКА ДУБЛИКАТОВ В КАРТРИДЖНОЙ БАЗЕ")
print("=" * 80)
print(f"Всего принтеров: {len(data)}")
print()

# Проверяем точные дубликаты по ключам
printer_names = list(data.keys())
duplicates = []
seen = set()

for name in printer_names:
    normalized = name.lower().strip()
    if normalized in seen:
        duplicates.append((normalized, name))
    else:
        seen.add(normalized)

if duplicates:
    print("[!] НАЙДЕНЫ ТОЧНЫЕ ДУБЛИКАТЫ (по нормализованным именам):")
    for norm, original in duplicates:
        print(f"  Дубликат: '{original}'")
else:
    print("[OK] Точных дубликатов нет")

print()

# Проверяем похожие названия (80%+ совпадение)
print("=" * 80)
print("ПОХОЖИЕ ПРИНТЕРЫ (80%+ совпадение):")
print("=" * 80)

similar_groups = []
processed = set()

for i, name1 in enumerate(printer_names):
    if name1 in processed:
        continue

    norm1 = name1.lower().strip()
    group = [name1]

    for j, name2 in enumerate(printer_names):
        if i == j or name2 in processed:
            continue

        norm2 = name2.lower().strip()
        ratio = SequenceMatcher(None, norm1, norm2).ratio()

        if ratio >= 0.8:  # 80% совпадение
            group.append(name2)
            processed.add(name2)

    if len(group) > 1:
        similar_groups.append(group)

if similar_groups:
    for group in similar_groups:
        print(f"\nГруппа ({len(group)} принтеров):")
        for name in group:
            print(f"  - {name}")
else:
    print("[OK] Похожих принтеров нет")

print()
print("=" * 80)
print("ПРИНТЕРЫ С WASTE_TONER:")
print("=" * 80)

waste_toner_printers = []
for name, data in data.items():
    if 'waste_toner_models' in data and data['waste_toner_models']:
        waste_toner_printers.append((name, data['waste_toner_models']))

if waste_toner_printers:
    for name, models in waste_toner_printers:
        print(f"{name}:")
        for model in models:
            print(f"  - {model}")
    print(f"\nВсего с waste_toner: {len(waste_toner_printers)}")
else:
    print("Нет принтеров с waste_toner")
