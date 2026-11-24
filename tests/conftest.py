import os

# Garante que os testes nunca usem o banco dev/produção por acidente.
# Os testes desta etapa substituem o banco por uma sessão falsa, então a URL não precisa existir.
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL") or "postgresql://teste:teste@localhost:1/teste"
