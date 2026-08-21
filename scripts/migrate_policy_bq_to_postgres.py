"""
Backfill de grants: BigQuery (`endpoint_data_access`) -> Postgres do app-pic
(tabela `policy`, no schema conforme APP_PIC_PG_SCHEMA no .env ativo — ver
plan.md seção 7), mais a coluna `users.secretarias_acesso`.

Escopo deste script:

1. Para cada usuário, gera linhas de `policy` (uma por item nas colunas
   id_cras_list, id_escola_list, id_cre_list, id_ap_list, id_cas_list,
   id_clinica_familia_list, id_equipe_familia_list) e, só para
   `is_super_admin=True`, uma linha "base" (unit_type/unit_id NULL,
   is_admin=True) que dá bypass total de RLS.
2. Converte o valor único legado `secretaria_acesso` (None/"NULL"/"TODOS"/
   "SME"/"SMS"/"SMAS") para a lista `users.secretarias_acesso` (subconjunto
   de {SME, SMS, SMAS}) — ver plan.md seção 3.1.

`secretaria_acesso` NÃO vira linha de `policy`: não é RLS-enforceable
nativamente (não é uma coluna flat da linha do participante, é usado pelo
app-pic para filtrar o array `protocolo_listagem` em Polars). Ver plan.md
seção 4.

`schema`/`synced_at`: `schema` é fixo (`env.DATA_PROXY_SCHEMA`, hoje
"app_pequenos_cariocas") por convenção com o schema do data-proxy, mas essa
etapa NÃO fala com o data-proxy — é só nomenclatura compartilhada.
`synced_at` fica sempre NULL (nada foi confirmado no data-proxy ainda).

Idempotente: para cada CPF migrado, faz DELETE de todas as linhas de `policy`
daquele subject antes de inserir as novas (evita duplicar linha "base" em
reruns — UNIQUE (schema, subject, unit_type, unit_id) não pega colisão de
NULL/NULL via ON CONFLICT, já que Postgres trata NULLs como distintos por
padrão). Pode ser rodado mais de uma vez sem duplicar.

Pré-requisito: scripts/migrate_users_bq_to_postgres.py já deve ter rodado
(policy.subject tem FK pra users.cpf).

EXECUÇÃO:
    python scripts/migrate_policy_bq_to_postgres.py --dry-run   # só mostra o que faria
    python scripts/migrate_policy_bq_to_postgres.py             # roda com confirmação
    python scripts/migrate_policy_bq_to_postgres.py --yes       # sem confirmação
"""

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

# Adicionar raiz do repo ao path para imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.api.v1.queries import GOVERNANCE_TABLE_QUERY
from src.config import env
from src.pic.infrastructure.admin.validation import _sanitize_cpf, _validate_cpf
from src.pic.infrastructure.db.engine import close_engine, get_session
from src.pic.infrastructure.db.models import PolicyRow, User
from src.utils.bigquery import execute_query
from src.utils.constants import (
    SECRETARIA_NULL,
    SECRETARIA_SMAS,
    SECRETARIA_SME,
    SECRETARIA_SMS,
    SECRETARIA_TODOS,
)
from src.utils.log import logger

SCHEMA = env.DATA_PROXY_SCHEMA

# Nome da coluna (BigQuery) -> unit_type (policy). Ordem sem importância.
GRANT_LIST_COLUMNS: dict[str, str] = {
    "id_cras_list": "cras",
    "id_escola_list": "escola",
    "id_cre_list": "cre",
    "id_ap_list": "ap",
    "id_cas_list": "cas",
    "id_clinica_familia_list": "clinica_familia",
    "id_equipe_familia_list": "equipe_familia",
}

ROW_COLUMNS = [
    "cpf",
    "is_admin",
    "is_super_admin",
    "active",
    "secretaria_acesso",
    *GRANT_LIST_COLUMNS.keys(),
]


def map_secretaria_acesso(value: str | None) -> list[str]:
    """Converte o valor único legado para a lista `users.secretarias_acesso`."""
    if value is None or value == SECRETARIA_NULL:
        return []
    if value == SECRETARIA_TODOS:
        return [SECRETARIA_SME, SECRETARIA_SMS, SECRETARIA_SMAS]
    if value in (SECRETARIA_SME, SECRETARIA_SMS, SECRETARIA_SMAS):
        return [value]
    logger.warning(f"secretaria_acesso com valor inesperado {value!r}, tratando como sem acesso")
    return []


def extract_unit_ids(items: list[Any] | None) -> set[str]:
    """Extrai o conjunto de unit_ids de uma lista de structs {id, nome}.

    Defensivo: replica a lógica de validation.py (`str(id_value).split(",")`)
    caso algum item tenha múltiplos ids concatenados por vírgula, embora os
    dados reais atuais não tenham nenhum caso assim.
    """
    unit_ids: set[str] = set()
    for item in items or []:
        id_value = item.get("id") if isinstance(item, dict) else getattr(item, "id", None)
        if not id_value:
            continue
        for single_id in str(id_value).split(","):
            single_id = single_id.strip()
            if single_id:
                unit_ids.add(single_id)
    return unit_ids


def fetch_and_validate_rows() -> tuple[list[dict], list[tuple[str, str]]]:
    """Busca a tabela de governança do BigQuery e valida os CPFs.

    Returns:
        (rows_validos, erros): rows_validos prontos pra virar linhas de
        `policy` + update de `secretarias_acesso`; erros é uma lista de
        (cpf_bruto, motivo) das linhas descartadas.
    """
    df = execute_query(GOVERNANCE_TABLE_QUERY)
    logger.info(f"BigQuery: {len(df)} linhas em endpoint_data_access")

    valid_rows: list[dict] = []
    errors: list[tuple[str, str]] = []
    seen_cpfs: set[str] = set()

    for row in df.select(ROW_COLUMNS).to_dicts():
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
        valid_rows.append(row)

    return valid_rows, errors


def build_policy_rows(row: dict) -> list[dict]:
    """Gera as linhas de `policy` para um usuário (sem `id`/timestamps)."""
    policy_rows: list[dict] = []

    if row["is_super_admin"]:
        policy_rows.append(
            {
                "schema": SCHEMA,
                "subject": row["cpf"],
                "is_admin": True,
                "is_enabled": row["active"],
                "unit_type": None,
                "unit_id": None,
                "synced_at": None,
            }
        )

    for list_col, unit_type in GRANT_LIST_COLUMNS.items():
        for unit_id in sorted(extract_unit_ids(row.get(list_col))):
            policy_rows.append(
                {
                    "schema": SCHEMA,
                    "subject": row["cpf"],
                    "is_admin": False,
                    "is_enabled": row["active"],
                    "unit_type": unit_type,
                    "unit_id": unit_id,
                    "synced_at": None,
                }
            )

    return policy_rows


def print_summary(rows: list[dict], errors: list[tuple[str, str]]) -> None:
    print("\n" + "=" * 80)
    print("BACKFILL policy + users.secretarias_acesso: BigQuery -> Postgres (app-pic)")
    print("=" * 80)
    print(f"\nUsuários válidos para migrar: {len(rows)}")

    total_grants = 0
    for row in rows:
        policy_rows = build_policy_rows(row)
        secretarias = map_secretaria_acesso(row["secretaria_acesso"])
        total_grants += len(policy_rows)
        base = " +base" if row["is_super_admin"] else ""
        print(
            f"  - {row['cpf']}: {len(policy_rows)} linha(s) de policy{base}, "
            f"secretarias_acesso={secretarias}"
        )

    print(f"\nTotal de linhas de policy a inserir: {total_grants}")

    if errors:
        print(f"\n⚠️  Linhas descartadas ({len(errors)}):")
        for raw_cpf, reason in errors:
            print(f"  - cpf={raw_cpf!r}: {reason}")
    print()


async def check_subjects_exist(cpfs: list[str]) -> list[str]:
    async with get_session() as session:
        result = await session.execute(select(User.cpf).where(User.cpf.in_(cpfs)))
        existing = {r[0] for r in result.all()}
    return [cpf for cpf in cpfs if cpf not in existing]


async def apply_policy_rows(rows: list[dict]) -> None:
    async with get_session() as session:
        for row in rows:
            cpf = row["cpf"]
            policy_rows = build_policy_rows(row)
            secretarias = map_secretaria_acesso(row["secretaria_acesso"])

            # DELETE+INSERT em vez de upsert: a linha "base" tem unit_type/
            # unit_id NULL, e Postgres trata NULLs como distintos numa
            # UNIQUE constraint por padrão, então ON CONFLICT não a
            # re-encontraria num rerun.
            await session.execute(
                delete(PolicyRow).where(PolicyRow.schema == SCHEMA, PolicyRow.subject == cpf)
            )
            if policy_rows:
                await session.execute(pg_insert(PolicyRow), policy_rows)

            await session.execute(
                update(User).where(User.cpf == cpf).values(secretarias_acesso=secretarias)
            )
        await session.commit()


async def verify(rows: list[dict]) -> None:
    expected_total = sum(len(build_policy_rows(row)) for row in rows)
    cpfs = [row["cpf"] for row in rows]

    async with get_session() as session:
        result = await session.execute(
            select(func.count())
            .select_from(PolicyRow)
            .where(PolicyRow.schema == SCHEMA, PolicyRow.subject.in_(cpfs))
        )
        actual_total = result.scalar_one()

        result = await session.execute(
            select(User.cpf, User.secretarias_acesso).where(User.cpf.in_(cpfs))
        )
        secretarias_by_cpf = dict(result.all())

    print(f"\n✅ Postgres agora tem {actual_total} linha(s) de policy pros CPFs migrados "
          f"na tabela `{PolicyRow.__tablename__}` (esperado: {expected_total}).")
    if actual_total != expected_total:
        print("❌ ATENÇÃO: contagem não bate.")
    else:
        print("✅ Contagem de linhas de policy confere.")

    mismatched = []
    for row in rows:
        expected_secretarias = sorted(map_secretaria_acesso(row["secretaria_acesso"]))
        actual_secretarias = sorted(secretarias_by_cpf.get(row["cpf"]) or [])
        if expected_secretarias != actual_secretarias:
            mismatched.append(row["cpf"])
    if mismatched:
        print(f"❌ ATENÇÃO: secretarias_acesso não bateu pra: {mismatched}")
    else:
        print(f"✅ secretarias_acesso confere pra todos os {len(rows)} usuário(s) na tabela "
              f"`{User.__tablename__}`.")


async def main(dry_run: bool, skip_confirmation: bool) -> None:
    try:
        rows, errors = fetch_and_validate_rows()
        print_summary(rows, errors)

        if not rows:
            print("Nada para migrar.\n")
            return

        missing_subjects = await check_subjects_exist([row["cpf"] for row in rows])
        if missing_subjects:
            print(
                f"❌ CPF(s) sem linha em `{User.__tablename__}` (rode "
                f"migrate_users_bq_to_postgres.py primeiro): {missing_subjects}\n"
            )
            return

        if dry_run:
            print("Modo --dry-run: nenhuma escrita foi feita.\n")
            return

        if not skip_confirmation:
            confirm = (
                input(f"Migrar grants de {len(rows)} usuário(s) para o Postgres? [s/N]: ")
                .strip()
                .lower()
            )
            if confirm not in ["s", "sim", "y", "yes"]:
                print("\n❌ Operação cancelada pelo usuário.\n")
                return

        print("\n🔄 Executando DELETE+INSERT de policy e update de secretarias_acesso...")
        await apply_policy_rows(rows)
        print("✅ Escrita concluída.")

        await verify(rows)
    finally:
        await close_engine()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Backfill de policy + users.secretarias_acesso: BigQuery (endpoint_data_access) -> Postgres app-pic"
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
