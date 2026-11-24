"""Valores permitidos para status e motivo, usados na validação da API.

O banco aplica as mesmas regras via CHECK constraints (geradas a partir destas listas).
"""
from enum import StrEnum


class StatusViagem(StrEnum):
    REALIZADA = "REALIZADA"
    NAO_REALIZADA = "NAO_REALIZADA"


class MotivoNaoRealizacao(StrEnum):
    MANUTENCAO = "MANUTENCAO"
    PESSOAL = "PESSOAL"
    TRANSITO = "TRANSITO"
    OPERACAO = "OPERACAO"
