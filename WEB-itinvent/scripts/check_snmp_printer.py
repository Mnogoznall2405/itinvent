#!/usr/bin/env python3
"""
Quick SNMP diagnostic for printer/MFU devices.

Usage:
  python WEB-itinvent/scripts/check_snmp_printer.py 10.109.0.57
  python WEB-itinvent/scripts/check_snmp_printer.py 10.109.0.57 --community mycommunity
"""
from __future__ import annotations

import argparse
import sys
import asyncio
from typing import Iterable, Optional, Tuple

try:
    from pysnmp.hlapi import (  # type: ignore
        CommunityData as LegacyCommunityData,
        ContextData as LegacyContextData,
        ObjectIdentity as LegacyObjectIdentity,
        ObjectType as LegacyObjectType,
        SnmpEngine as LegacySnmpEngine,
        UdpTransportTarget as LegacyUdpTransportTarget,
        getCmd as legacy_get_cmd,
    )
    _LEGACY_AVAILABLE = True
except Exception:
    _LEGACY_AVAILABLE = False

try:
    from pysnmp.hlapi.asyncio import (  # type: ignore
        CommunityData as AsyncCommunityData,
        ContextData as AsyncContextData,
        ObjectIdentity as AsyncObjectIdentity,
        ObjectType as AsyncObjectType,
        SnmpEngine as AsyncSnmpEngine,
        UdpTransportTarget as AsyncUdpTransportTarget,
        get_cmd as async_get_cmd,
    )
    _ASYNC_AVAILABLE = True
except Exception:
    _ASYNC_AVAILABLE = False

if not _LEGACY_AVAILABLE and not _ASYNC_AVAILABLE:
    print("[ERROR] pysnmp API import failed (legacy and asyncio variants).")
    print("Install/upgrade with: pip install -U pysnmp")
    sys.exit(2)


def snmp_get(ip: str, community: str, oid: str, mp_model: int, timeout: float) -> Tuple[bool, str]:
    if _LEGACY_AVAILABLE:
        iterator = legacy_get_cmd(
            LegacySnmpEngine(),
            LegacyCommunityData(community, mpModel=mp_model),  # 0=v1, 1=v2c
            LegacyUdpTransportTarget((ip, 161), timeout=timeout, retries=0),
            LegacyContextData(),
            LegacyObjectType(LegacyObjectIdentity(oid)),
        )
        error_indication, error_status, _error_index, var_binds = next(iterator)
        if error_indication:
            return False, f"error_indication: {error_indication}"
        if error_status:
            return False, f"error_status: {error_status.prettyPrint()}"
        for name, value in var_binds:
            rendered = value.prettyPrint()
            lowered = str(rendered).lower()
            if "no such" in lowered:
                return False, "no-such-object"
            return True, f"{name.prettyPrint()} = {rendered}"
        return False, "no-data"

    async def _query_async() -> Tuple[bool, str]:
        target = await AsyncUdpTransportTarget.create((ip, 161), timeout=timeout, retries=0)
        error_indication, error_status, _error_index, var_binds = await async_get_cmd(
            AsyncSnmpEngine(),
            AsyncCommunityData(community, mpModel=mp_model),  # 0=v1, 1=v2c
            target,
            AsyncContextData(),
            AsyncObjectType(AsyncObjectIdentity(oid)),
        )
        if error_indication:
            return False, f"error_indication: {error_indication}"
        if error_status:
            return False, f"error_status: {error_status.prettyPrint()}"
        for name, value in var_binds:
            rendered = value.prettyPrint()
            lowered = str(rendered).lower()
            if "no such" in lowered:
                return False, "no-such-object"
            return True, f"{name.prettyPrint()} = {rendered}"
        return False, "no-data"

    return asyncio.run(_query_async())


def probe(ip: str, community: str, timeout: float, max_idx: int) -> int:
    print(f"Target: {ip}")
    print(f"Community: {community}")
    print(f"Timeout: {timeout}s")
    print("-" * 60)

    modes: Iterable[Tuple[str, int]] = (("v2c", 1), ("v1", 0))
    selected_mode: Optional[Tuple[str, int]] = None

    for mode_name, mp_model in modes:
        ok_descr, val_descr = snmp_get(ip, community, "1.3.6.1.2.1.1.1.0", mp_model, timeout)
        ok_name, val_name = snmp_get(ip, community, "1.3.6.1.2.1.1.5.0", mp_model, timeout)
        print(f"[{mode_name}] sysDescr: {val_descr}")
        print(f"[{mode_name}] sysName : {val_name}")
        if ok_descr or ok_name:
            selected_mode = (mode_name, mp_model)
            break
        print(f"[{mode_name}] base OIDs failed, trying next mode...")

    if selected_mode is None:
        print("[RESULT] SNMP is not reachable with provided community (v2c/v1 failed).")
        return 1

    mode_name, mp_model = selected_mode
    print(f"[INFO] Using SNMP mode: {mode_name}")
    print("-" * 60)

    hits = 0
    for idx in range(1, max_idx + 1):
        descr_oid = f"1.3.6.1.2.1.43.11.1.1.6.1.{idx}"
        max_oid = f"1.3.6.1.2.1.43.11.1.1.8.1.{idx}"
        lvl_oid = f"1.3.6.1.2.1.43.11.1.1.9.1.{idx}"

        ok_descr, descr_val = snmp_get(ip, community, descr_oid, mp_model, timeout)
        ok_max, max_val = snmp_get(ip, community, max_oid, mp_model, timeout)
        ok_lvl, lvl_val = snmp_get(ip, community, lvl_oid, mp_model, timeout)

        if not (ok_descr or ok_max or ok_lvl):
            continue

        hits += 1
        print(f"[{idx}] DESC: {descr_val}")
        print(f"[{idx}] MAX : {max_val}")
        print(f"[{idx}] LVL : {lvl_val}")

        # Best-effort percent
        try:
            max_num = int(float(max_val.split("=", 1)[1].strip())) if "=" in max_val else None
            lvl_num = int(float(lvl_val.split("=", 1)[1].strip())) if "=" in lvl_val else None
            if max_num and lvl_num is not None and max_num > 0:
                pct = round((lvl_num / max_num) * 100)
                print(f"[{idx}] PCT : {pct}%")
        except Exception:
            pass
        print("-" * 40)

    if hits == 0:
        print("[RESULT] SNMP reachable, but Printer-MIB supply OIDs returned no data.")
        return 3

    print(f"[RESULT] OK, found {hits} supply slot(s).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="SNMP printer diagnostic")
    parser.add_argument("ip", help="Printer IP address")
    parser.add_argument("--community", default="public", help="SNMP community (default: public)")
    parser.add_argument("--timeout", type=float, default=1.5, help="SNMP timeout seconds (default: 1.5)")
    parser.add_argument("--max-idx", type=int, default=12, help="Max supply index to test (default: 12)")
    args = parser.parse_args()

    return probe(
        ip=args.ip,
        community=args.community,
        timeout=max(0.5, args.timeout),
        max_idx=max(1, args.max_idx),
    )


if __name__ == "__main__":
    raise SystemExit(main())
