"""Restaura a carga inicial: apaga TODAS as viagens, linhas e empresas e reimporta o CSV.

Operação destrutiva. Para evitar executar no banco errado, é obrigatório informar o
identificador do banco de destino (no Neon, o endpoint 'ep-...' que aparece no host da
DATABASE_URL). Se não coincidir com o banco configurado, nada é feito.

Uso (na raiz do projeto):
    python -m scripts.reset_db --confirmar ep-xxxx-yyyy
"""
import argparse
import sys
from pathlib import Path

from sqlalchemy import func, select

from app.database import SessionLocal, identificacao_banco
from app.models import Viagem
from app.services.importacao import CAMINHO_PADRAO, ErroImportacao, ler_csv, proximo_id_viagem, resetar


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Restaura a base de demonstração a partir do CSV.")
    parser.add_argument(
        "--confirmar",
        required=True,
        metavar="IDENTIFICADOR",
        help="identificador do banco de destino (ex.: ep-xxxx-yyyy); precisa coincidir com DATABASE_URL",
    )
    parser.add_argument("--arquivo", type=Path, default=CAMINHO_PADRAO, help="caminho do CSV")
    args = parser.parse_args(argv)

    alvo = identificacao_banco()
    if args.confirmar != alvo:
        print(f"RECUSADO: o banco configurado é '{alvo}', mas foi confirmado '{args.confirmar}'.")
        print("Nada foi alterado.")
        return 2

    # Valida o arquivo ANTES de apagar qualquer coisa.
    try:
        registros = ler_csv(args.arquivo)
    except ErroImportacao as erro:
        print(f"ERRO no arquivo: {erro}")
        for detalhe in erro.erros[:50]:
            print(f"  - {detalhe}")
        return 1

    with SessionLocal() as db:
        antes = db.scalar(select(func.count()).select_from(Viagem))
        resultado = resetar(db, registros)
        proximo = proximo_id_viagem(db)

    print(f"Banco: {alvo}")
    print(f"Viagens antes do reset: {antes}")
    print(f"Viagens após o reset:   {resultado.inseridos}")
    print(f"Próximo id_viagem:      {proximo}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
