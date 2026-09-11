import ctypes
import json
import platform
import sqlite3
import ssl
import sys
import sysconfig
from ctypes import wintypes

kernel = ctypes.WinDLL("kernel32", use_last_error=True)


class MachineInformation(ctypes.Structure):
    _fields_ = [("machine", wintypes.USHORT), ("reserved", wintypes.USHORT), ("attributes", wintypes.DWORD)]


kernel.GetCurrentProcess.restype = wintypes.HANDLE
kernel.GetProcessInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.POINTER(MachineInformation), wintypes.DWORD]
kernel.GetProcessInformation.restype = wintypes.BOOL
kernel.IsWow64Process2.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.USHORT), ctypes.POINTER(wintypes.USHORT)]
kernel.IsWow64Process2.restype = wintypes.BOOL
process_machine = wintypes.USHORT()
native_machine = wintypes.USHORT()
if not kernel.IsWow64Process2(kernel.GetCurrentProcess(), ctypes.byref(process_machine), ctypes.byref(native_machine)):
    raise ctypes.WinError(ctypes.get_last_error())
information = MachineInformation()
if not kernel.GetProcessInformation(kernel.GetCurrentProcess(), 9, ctypes.byref(information), ctypes.sizeof(information)):
    raise ctypes.WinError(ctypes.get_last_error())
result = {
    "executable": sys.executable,
    "version": sys.version,
    "machine": platform.machine(),
    "platform": sysconfig.get_platform(),
    "pointer_bits": ctypes.sizeof(ctypes.c_void_p) * 8,
    "wow64_process_machine": hex(process_machine.value),
    "process_machine": hex(information.machine),
    "native_machine": hex(native_machine.value),
    "native_arm64": information.machine == native_machine.value == 0xAA64 and sysconfig.get_platform() == "win-arm64",
    "ssl": ssl.OPENSSL_VERSION,
    "sqlite": sqlite3.sqlite_version,
}
print(json.dumps(result, indent=2))
if not result["native_arm64"]:
    sys.exit(1)
