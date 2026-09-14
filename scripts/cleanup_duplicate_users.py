"""
Script para limpar registros duplicados na tabela de governança.

Este script:
1. Identifica CPFs duplicados
2. Mantém apenas o registro mais apropriado (super admin > admin > user)
3. Deleta os registros duplicados

EXECUÇÃO:
    python scripts/cleanup_duplicate_users.py

    Ou sem confirmação (modo não-interativo):
    python scripts/cleanup_duplicate_users.py --yes

IMPORTANTE: Faça backup antes de executar!
"""

import argparse
import sys
from pathlib import Path

# Adicionar src ao path para imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import env
from src.utils.bigquery import execute_query
from src.utils.log import logger

# Tabela de governança
PROJECT_ID = env.BQ_PROJECT_ID
DATASET_ID = env.BQ_DATASET_ID
TABLE_ID_DATA_ACCESS = env.BQ_TABLE_ID_DATA_ACCESS


def find_duplicates():
    """Encontra CPFs duplicados na tabela"""
    query = f"""
    SELECT
        cpf,
        COUNT(*) as total,
        ARRAY_AGG(
            STRUCT(
                is_super_admin,
                is_admin,
                permission,
                created_at,
                active
            )
            ORDER BY
                is_super_admin DESC,
                is_admin DESC,
                created_at DESC
        ) as registros
    FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID_DATA_ACCESS}`
    GROUP BY cpf
    HAVING COUNT(*) > 1
    ORDER BY cpf
    """

    try:
        result = execute_query(query)
        return result
    except Exception as e:
        logger.error(f"❌ Erro ao buscar duplicados: {e}")
        return None


def show_duplicates(duplicates_df):
    """Exibe CPFs duplicados de forma formatada"""
    if duplicates_df.is_empty():
        print("✅ Nenhum CPF duplicado encontrado!\n")
        return False

    print(f"\n⚠️  Encontrados {len(duplicates_df)} CPFs duplicados:\n")
    print("=" * 80)

    for row in duplicates_df.iter_rows(named=True):
        cpf = row['cpf']
        total = row['total']
        registros = row['registros']

        print(f"\n📋 CPF: {cpf} ({total} registros)")
        print("-" * 80)

        for i, reg in enumerate(registros, 1):
            tipo = "SUPER ADMIN" if reg['is_super_admin'] else ("ADMIN" if reg['is_admin'] else "USER")
            status = "ATIVO" if reg['active'] else "INATIVO"
            created = reg['created_at'].strftime('%Y-%m-%d %H:%M:%S') if reg['created_at'] else "N/A"

            marker = "✓ MANTER" if i == 1 else "✗ DELETAR"
            print(f"  {i}. [{marker}] {tipo:<12} | {status:<8} | Criado: {created}")

    print("\n" + "=" * 80)
    print("\n💡 Estratégia de limpeza:")
    print("   - Mantém: Super Admin > Admin > User (mais recente)")
    print("   - Deleta: Todos os outros registros do mesmo CPF\n")

    return True


def cleanup_duplicates(cpf: str):
    """
    Remove registros duplicados de um CPF, mantendo apenas o mais apropriado.

    Critério de prioridade:
    1. is_super_admin = TRUE
    2. is_admin = TRUE
    3. created_at (mais recente)
    """
    query = f"""
    -- Deletar registros duplicados mantendo apenas o melhor
    DELETE FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID_DATA_ACCESS}`
    WHERE cpf = '{cpf}'
      AND created_at NOT IN (
        -- Seleciona o registro a manter (melhor match)
        SELECT created_at
        FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID_DATA_ACCESS}`
        WHERE cpf = '{cpf}'
        ORDER BY
            is_super_admin DESC,  -- Super admin primeiro
            is_admin DESC,         -- Admin segundo
            created_at DESC        -- Mais recente terceiro
        LIMIT 1
      )
    """

    try:
        execute_query(query)
        return True
    except Exception as e:
        logger.error(f"❌ Erro ao limpar duplicados do CPF {cpf}: {e}")
        return False


def cleanup_all_duplicates(skip_confirmation: bool = False):
    """Limpa todos os CPFs duplicados"""
    print("\n" + "=" * 80)
    print("🧹 LIMPEZA DE REGISTROS DUPLICADOS")
    print("=" * 80)

    # Buscar duplicados
    print("\n🔍 Buscando CPFs duplicados...")
    duplicates_df = find_duplicates()

    if duplicates_df is None:
        print("❌ Erro ao buscar duplicados. Abortando.\n")
        return

    # Mostrar duplicados
    has_duplicates = show_duplicates(duplicates_df)

    if not has_duplicates:
        return

    # Confirmar limpeza
    if not skip_confirmation:
        print("⚠️  ATENÇÃO: Esta operação é IRREVERSÍVEL!")
        print("   Registros deletados NÃO podem ser recuperados.\n")
        confirm = input("Deseja prosseguir com a limpeza? [s/N]: ").strip().lower()

        if confirm not in ["s", "sim", "y", "yes"]:
            print("\n❌ Operação cancelada pelo usuário.\n")
            return
    else:
        print("⚠️  Modo não-interativo: limpando duplicados sem confirmação...\n")

    # Executar limpeza
    print("\n🔄 Limpando registros duplicados...\n")

    success_count = 0
    error_count = 0

    for row in duplicates_df.iter_rows(named=True):
        cpf = row['cpf']
        total = row['total']

        print(f"  🧹 Limpando CPF {cpf}...", end=" ")

        if cleanup_duplicates(cpf):
            registros_deletados = total - 1
            print(f"✅ OK ({registros_deletados} registro(s) deletado(s))")
            success_count += 1
        else:
            print("❌ ERRO")
            error_count += 1

    # Refresh cache
    print("\n🔄 Atualizando cache de governança...")
    try:
        from src.api.v1.queries import GOVERNANCE_TABLE_QUERY
        from src.utils.data_manager import DataManager

        DataManager.get_dataset(GOVERNANCE_TABLE_QUERY, bypass_cache=True)
        print("✅ Cache atualizado\n")
    except Exception as e:
        print(f"⚠️  Aviso: Não foi possível atualizar cache: {e}")
        print("   O cache será atualizado automaticamente na próxima request.\n")

    # Resumo
    print("=" * 80)
    print("🎉 LIMPEZA CONCLUÍDA")
    print("=" * 80)
    print(f"\n✅ Sucesso: {success_count} CPF(s)")
    if error_count > 0:
        print(f"❌ Erros: {error_count} CPF(s)")
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Script de limpeza de registros duplicados"
    )
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Pular confirmação (modo não-interativo)",
    )
    args = parser.parse_args()

    try:
        cleanup_all_duplicates(skip_confirmation=args.yes)
    except KeyboardInterrupt:
        print("\n\n❌ Operação cancelada pelo usuário.\n")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Erro inesperado: {e}\n")
        logger.error(f"❌ Erro inesperado na limpeza: {e}", exc_info=True)
        sys.exit(1)
