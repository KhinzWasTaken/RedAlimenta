"""Errores de dominio con un formato único de respuesta: {"detail": "..."}."""


class ErrorDominio(Exception):
    codigo = 400

    def __init__(self, mensaje: str):
        super().__init__(mensaje)
        self.mensaje = mensaje


class NoEncontrado(ErrorDominio):
    codigo = 404


class Prohibido(ErrorDominio):
    codigo = 403


class Conflicto(ErrorDominio):
    codigo = 409


class TransicionInvalida(Conflicto):
    """Transición de estado no permitida por docs/modelo/estados.md."""
