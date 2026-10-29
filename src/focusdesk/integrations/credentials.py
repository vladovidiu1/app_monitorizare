"""Windows Credential Manager; never a file-based or fixed-key fallback.

The system DLL is loaded lazily. Non-Windows machines can use session memory.
Native errors intentionally contain no credentials or untrusted OS details.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import sys
from ..domain.common import is_uuid


class CredentialUnavailable(Exception):
    def __init__(self):
        super().__init__('Secure credential storage unavailable')


class _Credential(ctypes.Structure):
    _fields_ = [('Flags',wintypes.DWORD),('Type',wintypes.DWORD),
                ('TargetName',wintypes.LPWSTR),('Comment',wintypes.LPWSTR),
                ('LastWritten',wintypes.FILETIME),('CredentialBlobSize',wintypes.DWORD),
                ('CredentialBlob',ctypes.POINTER(ctypes.c_ubyte)),('Persist',wintypes.DWORD),
                ('AttributeCount',wintypes.DWORD),('Attributes',ctypes.c_void_p),
                ('TargetAlias',wintypes.LPWSTR),('UserName',wintypes.LPWSTR)]


class WindowsCredentialStore:
    def _api(self):
        if sys.platform != 'win32':raise CredentialUnavailable()
        try:
            api=ctypes.WinDLL('Advapi32.dll',use_last_error=True)
            api.CredWriteW.argtypes=[ctypes.POINTER(_Credential),wintypes.DWORD]
            api.CredWriteW.restype=wintypes.BOOL
            api.CredReadW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.POINTER(ctypes.POINTER(_Credential))]
            api.CredReadW.restype=wintypes.BOOL
            api.CredDeleteW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD]
            api.CredDeleteW.restype=wintypes.BOOL
            api.CredFree.argtypes=[ctypes.c_void_p];api.CredFree.restype=None
            return api
        except (AttributeError,OSError):raise CredentialUnavailable() from None

    @property
    def available(self):
        try:self._api();return True
        except CredentialUnavailable:return False

    def _target(self,profile_id):
        if not is_uuid(profile_id):raise CredentialUnavailable()
        return 'FocusDesk/Gmail/'+profile_id

    def get(self,profile_id):
        api=self._api();pointer=ctypes.POINTER(_Credential)()
        if not api.CredReadW(self._target(profile_id),1,0,ctypes.byref(pointer)):
            if ctypes.get_last_error()==1168:return None  # ERROR_NOT_FOUND
            raise CredentialUnavailable()
        try:
            value=pointer.contents
            return ctypes.string_at(value.CredentialBlob,value.CredentialBlobSize).decode('utf-16-le')
        except (UnicodeError,ValueError):raise CredentialUnavailable() from None
        finally:api.CredFree(pointer)

    def set(self,profile_id,address,password):
        api=self._api();raw=password.encode('utf-16-le')
        if len(raw)>2560:raise CredentialUnavailable()
        blob=(ctypes.c_ubyte*len(raw)).from_buffer_copy(raw)
        cred=_Credential();cred.Type=1;cred.TargetName=self._target(profile_id)
        cred.UserName=address;cred.CredentialBlobSize=len(raw);cred.CredentialBlob=blob
        cred.Persist=2  # CRED_PERSIST_LOCAL_MACHINE: this user's logons on this computer
        try:
            if not api.CredWriteW(ctypes.byref(cred),0):raise CredentialUnavailable()
        finally:ctypes.memset(blob,0,len(raw))

    def delete(self,profile_id):
        api=self._api()
        if not api.CredDeleteW(self._target(profile_id),1,0) and ctypes.get_last_error()!=1168:
            raise CredentialUnavailable()
