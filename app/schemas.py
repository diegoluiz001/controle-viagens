"""Modelos Pydantic: o formato dos dados que entram e saem da API.

A regra de negócio status/motivo é validada aqui (mensagem clara para o usuário)
e também no banco, pelo CHECK status_motivo_coerente (rede de segurança).
"""
from datetime import date, datetime, time
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PlainSerializer,
    field_validator,
    model_validator,
)
from pydantic_core import PydanticCustomError

from app.enums import MotivoNaoRealizacao, StatusViagem
from app.models import Viagem

# Horário sempre devolvido como "HH:MM" (sem segundos), igual ao arquivo de origem.
HorarioHHMM = Annotated[time, PlainSerializer(lambda t: t.strftime("%H:%M"), return_type=str)]

# Mensagens reaproveitadas pelos testes e pela interface.
MSG_REALIZADA_COM_MOTIVO = "viagem REALIZADA não pode ter motivo_nao_realizacao"
MSG_NAO_REALIZADA_SEM_MOTIVO = (
    "viagem NAO_REALIZADA exige motivo_nao_realizacao (MANUTENCAO, PESSOAL, TRANSITO ou OPERACAO)"
)


# --------------------------------------------------------------------------- filtros


class FiltroViagens(BaseModel):
    """Filtros combináveis, usados IGUALMENTE pela listagem e pelos indicadores.

    Todos são opcionais. As datas são inclusivas: data_inicio <= data_viagem <= data_fim.
    """

    data_inicio: date | None = None
    data_fim: date | None = None
    empresa_id: int | None = Field(default=None, gt=0)
    linha_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def periodo_coerente(self):
        if self.data_inicio and self.data_fim and self.data_inicio > self.data_fim:
            raise PydanticCustomError("periodo_invalido", "data_inicio não pode ser posterior a data_fim")
        return self


# --------------------------------------------------------------------------- entrada


class ViagemEntrada(BaseModel):
    """Corpo do POST (criação) e do PUT (edição completa).

    O id_viagem NÃO faz parte do corpo: é gerado pelo servidor na criação e é imutável.
    extra="forbid" recusa campos desconhecidos (inclusive uma tentativa de enviar id_viagem).
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    linha_id: int = Field(gt=0)
    data_viagem: date
    horario_programado: time = Field(description="Horário local no formato HH:MM, sem fuso")
    veiculo: str = Field(min_length=1, max_length=30)
    status: StatusViagem
    motivo_nao_realizacao: MotivoNaoRealizacao | None = None

    @field_validator("motivo_nao_realizacao", mode="before")
    @classmethod
    def motivo_vazio_vira_nulo(cls, valor):
        """O formulário envia "" quando nenhum motivo é escolhido; isso significa 'sem motivo'."""
        if isinstance(valor, str) and not valor.strip():
            return None
        return valor

    @field_validator("horario_programado")
    @classmethod
    def horario_sem_segundos_nem_fuso(cls, valor: time) -> time:
        if valor.tzinfo is not None:
            raise PydanticCustomError("horario_formato", "horario_programado é horário local, sem fuso horário (HH:MM)")
        if valor.second or valor.microsecond:
            raise PydanticCustomError("horario_formato", "horario_programado deve estar no formato HH:MM")
        return valor

    @model_validator(mode="after")
    def regra_status_motivo(self):
        """Regra de integridade do desafio (item 05)."""
        if self.status == StatusViagem.REALIZADA and self.motivo_nao_realizacao is not None:
            raise PydanticCustomError("status_motivo", MSG_REALIZADA_COM_MOTIVO)
        if self.status == StatusViagem.NAO_REALIZADA and self.motivo_nao_realizacao is None:
            raise PydanticCustomError("status_motivo", MSG_NAO_REALIZADA_SEM_MOTIVO)
        return self


# --------------------------------------------------------------------------- saída


class ViagemSaida(BaseModel):
    id_viagem: str
    data_viagem: date
    horario_programado: HorarioHHMM
    veiculo: str
    status: StatusViagem
    motivo_nao_realizacao: MotivoNaoRealizacao | None
    empresa_id: int
    empresa_codigo: str
    empresa_nome: str
    linha_id: int
    linha_codigo: str
    linha_descricao: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def de_modelo(cls, viagem: Viagem) -> "ViagemSaida":
        linha = viagem.linha
        empresa = linha.empresa
        return cls(
            id_viagem=viagem.id_viagem,
            data_viagem=viagem.data_viagem,
            horario_programado=viagem.horario_programado,
            veiculo=viagem.veiculo,
            status=viagem.status,
            motivo_nao_realizacao=viagem.motivo_nao_realizacao,
            empresa_id=empresa.id,
            empresa_codigo=empresa.codigo,
            empresa_nome=empresa.nome,
            linha_id=linha.id,
            linha_codigo=linha.codigo,
            linha_descricao=linha.descricao,
            created_at=viagem.created_at,
            updated_at=viagem.updated_at,
        )


class ListaViagens(BaseModel):
    total: int = Field(description="Quantidade de viagens que atendem aos filtros (todas as páginas)")
    pagina: int
    por_pagina: int
    itens: list[ViagemSaida]


class LinhaSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    codigo: str
    descricao: str


class EmpresaSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    codigo: str
    nome: str
    linhas: list[LinhaSaida]
