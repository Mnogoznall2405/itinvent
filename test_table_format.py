#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test new table format for cartridge export
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import asyncio
from bot.handlers.export import export_cartridges_to_excel_structured

async def test_table_format():
    print("Testing new table format for cartridge export...")
    try:
        # Test with a small period to limit API calls
        result = await export_cartridges_to_excel_structured(period="all")
        if result:
            print(f"SUCCESS: Table format file created at {result}")
        else:
            print("FAILED: No result returned")
    except Exception as e:
        print(f"ERROR: {e}")
        print(f"Type: {type(e).__name__}")

if __name__ == "__main__":
    asyncio.run(test_table_format())