#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test Russian periods in cartridge export
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import asyncio
from bot.handlers.export import export_cartridges_to_excel_structured, get_period_name_ru

async def test_russian_periods():
    print("Testing Russian periods...")

    # Test period conversion
    periods = ['1month', '3months', 'all']
    for period in periods:
        ru_name = get_period_name_ru(period)
        print(f"{period} -> {ru_name}")

    # Test export with Russian periods
    try:
        result = await export_cartridges_to_excel_structured(period="1month")
        if result:
            print(f"SUCCESS: Russian periods file created at {result}")
        else:
            print("FAILED: No result returned")
    except Exception as e:
        print(f"ERROR: {e}")
        print(f"Type: {type(e).__name__}")

if __name__ == "__main__":
    asyncio.run(test_russian_periods())