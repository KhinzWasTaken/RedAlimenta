"""Errores de dominio. La API (Sprint 5) los traduce a códigos HTTP."""


class ErrorDominio(Exception):
    codigo = 400


class NoEncontrado(ErrorDominio):
    codigo = 404


class Conflicto(ErrorDominio):
    codigo = 409


class TransicionInvalida(Conflicto):
    """Transición de estado no permitida por docs/modelo/estados.md."""
