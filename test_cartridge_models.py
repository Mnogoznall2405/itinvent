#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test cartridge models in table format
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import asyncio
from bot.handlers.export import export_cartridges_to_excel_structured

async def test_cartridge_models():
    print("Testing cartridge models in export...")
    try:
        # Test with all data to get maximum results
        result = await export_cartridges_to_excel_structured(period="all")
        if result:
            print(f"SUCCESS: Cartridge models file created at {result}")
        else:
            print("FAILED: No result returned")
    except Exception as e:
        print(f"ERROR: {e}")
        print(f"Type: {type(e).__name__}")

if __name__ == "__main__":
    asyncio.run(test_cartridge_models())