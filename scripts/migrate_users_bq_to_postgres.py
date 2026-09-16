"""
Backfill de identidade de usuários: BigQuery (`endpoint_data_access`) -> Postgres
do app-pic (tabela `users`, no schema conforme APP_PIC_PG_SCHEMA no .env ativo —
ver plan.md seção 7).

Escopo deste script (ver plan.md seções 3.1 e 10.9): migra só os campos de
IDENTIDADE (cpf, nome, email, ocupacao, secretaria, is_admin, is_super_admin,
active, notes, created_by/updated_by, created_at/updated_at).

NÃO migra grants (id_cras_list, id_escola_list, id_cre_list, id_ap_list,
id_cas_list, id_clinica_familia_list, id_equipe_familia_list,
secretaria_acesso) — isso vira linhas da tabela `policy`, e só deve ser escrito
depois de confirmado no data-proxy (`rls.access_policy`), que ainda não foi
implementado. Ver plan.md seção 5.

Idempotente: usa UPSERT (ON CONFLICT (cpf) DO UPDATE), pode ser rodado mais de
uma vez sem duplicar ou falhar.

EXECUÇÃO:
    python scripts/migrate_users_bq_to_postgres.py --dry-run   # só mostra o que faria
    python scripts/migrate_users_bq_to_postgres.py             # roda com confirmação
    python scripts/migrate_users_bq_to_postgres.py --yes       # sem confirmação
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Adicionar raiz do repo ao path para imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.api.v1.queries import GOVERNANCE_TABLE_QUERY
from src.pic.infrastructure.admin.validation import _sanitize_cpf, _validate_cpf
from src.pic.infrastructure.db.engine import close_engine, get_session
from src.pic.infrastructure.db.models import User
from src.utils.bigquery import execute_query
from src.utils.log import logger

USER_COLUMNS = [
    "cpf",
    "nome",
    "email",
    "ocupacao",
    "secretaria",
    "is_admin",
    "is_super_admin",
    "active",
    "notes",
    "created_by",
    "updated_by",
    "created_at",
    "updated_at",
]


def fetch_and_validate_rows() -> tuple[list[dict], list[tuple[str, str]]]:
    """Busca a tabela de governança do BigQuery e valida os CPFs.

    Returns:
        (rows_validos, erros): rows_validos prontos pra upsert; erros é uma
        lista de (cpf_bruto, motivo) das linhas descartadas.
    """
    df = execute_query(GOVERNANCE_TABLE_QUERY)
    logger.info(f"BigQuery: {len(df)} linhas em endpoint_data_access")

    valid_rows: list[dict] = []
    errors: list[tuple[str, str]] = []
    seen_cpfs: set[str] = set()

    for row in df.select(USER_COLUMNS).to_dicts():
        raw_cpf = row["cpf"]
        cpf = _sanitize_cpf(raw_cpf)
        error = _validate_cpf(cpf)
        if error:
            errors.append((raw_cpf, error))
            continue
        if cpf in seen_cpfs:
            errors.append((raw_cpf, "CPF duplicado na origem (BigQuery)"))
            continue
        seen_cpfs.add(cpf)
        row["cpf"] = cpf
        # `updated_at` pode ser NULL no BigQuery (o INSERT original não o
        # preenche) — a coluna é NOT NULL no Postgres, então usamos created_at
        # como fallback.
        if row["updated_at"] is None:
            row["updated_at"] = row["created_at"]
        valid_rows.append(row)

    return valid_rows, errors


def print_summary(rows: list[dict], errors: list[tuple[str, str]]) -> None:
    print("\n" + "=" * 80)
    print("BACKFILL users: BigQuery -> Postgres (app-pic)")
    print("=" * 80)
    print(f"\nLinhas válidas para migrar: {len(rows)}")
    for row in rows:
        flags = []
        if row["is_super_admin"]:
            flags.append("SUPER_ADMIN")
        elif row["is_admin"]:
            flags.append("ADMIN")
        if not row["active"]:
            flags.append("INATIVO")
        flags_str = f" [{', '.join(flags)}]" if flags else ""
        print(f"  - {row['cpf']} {row['nome']!r}{flags_str}")

    if errors:
        print(f"\n⚠️  Linhas descartadas ({len(errors)}):")
        for raw_cpf, reason in errors:
            print(f"  - cpf={raw_cpf!r}: {reason}")

    print(
        "\nNOTA: grants (id_cras_list, id_escola_list, id_cre_list, id_ap_list, "
        "id_cas_list, id_clinica_familia_list, id_equipe_familia_list, "
        "secretaria_acesso) NÃO são migrados por este script — ficam para a "
        "etapa do data-proxy (plan.md seção 5).\n"
    )


async def upsert_users(rows: list[dict]) -> None:
    stmt_base = pg_insert(User)
    async with get_session() as session:
        for row in rows:
            stmt = stmt_base.values(**row)
            stmt = stmt.on_conflict_do_update(
                index_elements=[User.cpf],
                set_={col: stmt.excluded[col] for col in USER_COLUMNS if col != "cpf"},
            )
            await session.execute(stmt)
        await session.commit()


async def verify(rows: list[dict]) -> None:
    expected_cpfs = {row["cpf"] for row in rows}
    async with get_session() as session:
        result = await session.execute(select(func.count()).select_from(User))
        total = result.scalar_one()
        result = await session.execute(select(User.cpf))
        actual_cpfs = {r[0] for r in result.all()}

    missing = expected_cpfs - actual_cpfs
    print(f"\n✅ Postgres agora tem {total} usuário(s) na tabela `{User.__tablename__}`.")
    if missing:
        print(f"❌ ATENÇÃO: {len(missing)} CPF(s) esperados não foram encontrados: {missing}")
    else:
        print("✅ Todos os CPFs migrados foram confirmados no Postgres.")


async def main(dry_run: bool, skip_confirmation: bool) -> None:
    try:
        rows, errors = fetch_and_validate_rows()
        print_summary(rows, errors)

        if not rows:
            print("Nada para migrar.\n")
            return

        if dry_run:
            print("Modo --dry-run: nenhuma escrita foi feita.\n")
            return

        if not skip_confirmation:
            confirm = input(f"Migrar {len(rows)} usuário(s) para o Postgres? [s/N]: ").strip().lower()
            if confirm not in ["s", "sim", "y", "yes"]:
                print("\n❌ Operação cancelada pelo usuário.\n")
                return

        print("\n🔄 Executando upsert...")
        await upsert_users(rows)
        print("✅ Upsert concluído.")

        await verify(rows)
    finally:
        await close_engine()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Backfill de users: BigQuery (endpoint_data_access) -> Postgres app-pic"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Só mostra o que seria migrado, sem escrever no Postgres",
    )
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Pular confirmação (modo não-interativo)",
    )
    args = parser.parse_args()

    try:
        asyncio.run(main(dry_run=args.dry_run, skip_confirmation=args.yes))
    except KeyboardInterrupt:
        print("\n\n❌ Operação cancelada pelo usuário.\n")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Erro inesperado: {e}\n")
        logger.error(f"❌ Erro inesperado no backfill: {e}", exc_info=True)
        sys.exit(1)
