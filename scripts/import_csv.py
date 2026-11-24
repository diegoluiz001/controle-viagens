"""Importa o CSV de viagens para o banco configurado em DATABASE_URL.

Pode ser executado quantas vezes for preciso: viagens já existentes (mesmo id_viagem)
são ignoradas, nunca duplicadas.

Uso (na raiz do projeto):
    python -m scripts.import_csv
    python -m scripts.import_csv --arquivo caminho/para/outro.csv
"""
import argparse
import sys
from pathlib import Path

from app.database import SessionLocal, identificacao_banco
from app.services.importacao import CAMINHO_PADRAO, ErroImportacao, importar, ler_csv, proximo_id_viagem


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Importa o CSV de viagens (sem duplicar).")
    parser.add_argument("--arquivo", type=Path, default=CAMINHO_PADRAO, help="caminho do CSV")
    args = parser.parse_args(argv)

    print(f"Banco de destino: {identificacao_banco()}")
    print(f"Arquivo:          {args.arquivo}")

    try:
        registros = ler_csv(args.arquivo)
    except ErroImportacao as erro:
        print(f"\nERRO: {erro}")
        for detalhe in erro.erros[:50]:
            print(f"  - {detalhe}")
        return 1

    with SessionLocal() as db:
        resultado = importar(db, registros)
        proximo = proximo_id_viagem(db)

    print()
    print(f"Registros lidos no arquivo: {resultado.lidos}")
    print(f"Viagens importadas:         {resultado.inseridos}")
    print(f"Viagens já existentes:      {resultado.existentes}")
    print(f"Empresas novas:             {resultado.empresas_novas}")
    print(f"Linhas novas:               {resultado.linhas_novas}")
    print(f"Próximo id_viagem:          {proximo}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
