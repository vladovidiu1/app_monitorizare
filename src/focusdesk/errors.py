"""Exceptii specifice aplicatiei."""

from __future__ import annotations


class FocusDeskError(Exception):
    """Baza tuturor erorilor aplicatiei; mesajul este afisabil utilizatorului."""


class StorageError(FocusDeskError):
    pass


class ReadOnlyError(StorageError):
    pass


class WorkspaceLockedError(StorageError):
    pass


class ExternalModificationError(StorageError):
    """Fisierul a fost modificat din afara aplicatiei dupa ultima citire."""


class CorruptFileError(StorageError):
    pass


class PathTooLongError(StorageError):
    pass


class UnsafePathError(StorageError):
    pass


class ValidationError(FocusDeskError):
    pass


class CycleError(ValidationError):
    pass


class NotFoundError(FocusDeskError):
    pass
