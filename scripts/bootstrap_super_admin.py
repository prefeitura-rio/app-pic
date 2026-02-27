"""
Bootstrap script para criar ou atualizar super admins no sistema de governança.

Este script:
1. Cria a tabela data_access automaticamente se não existir
2. Cria o primeiro super admin com acesso total ao sistema E TODOS OS CAMPOS PREENCHIDOS
3. Atualiza informações de super admins existentes (se já existir um com o CPF configurado)
4. O super admin poderá criar outros admins via interface web

CONFIGURAÇÃO:
- Edite as variáveis SUPER_ADMIN_* nas linhas 42-48:
  * SUPER_ADMIN_CPF: CPF do super admin (11 dígitos, sem pontos/traços)
  * SUPER_ADMIN_NAME: Nome completo
  * SUPER_ADMIN_EMAIL: Email corporativo
  * SUPER_ADMIN_OCUPACAO: Cargo/função
  * SUPER_ADMIN_SECRETARIA: Secretaria/órgão
- CPF deve ser o mesmo que vem do login gov.br (campo preferred_username do JWT)

EXECUÇÃO:
    python scripts/bootstrap_super_admin.py

    Ou sem confirmação (modo não-interativo):
    python scripts/bootstrap_super_admin.py --yes

ATUALIZAÇÃO DE SUPER ADMIN EXISTENTE:
    Se já existe um super admin com o CPF configurado, o script perguntará
    se você deseja atualizar as informações dele. Útil para completar
    campos que estavam NULL ou vazios.

VALIDAÇÃO:
    Após executar, tente fazer login com o CPF configurado.
    Você deve ter acesso total ao sistema e ver o menu Admin.
"""

import sys
import argparse
from pathlib import Path

# Adicionar src ao path para imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import env
from src.utils.bigquery import execute_query
from src.utils.log import logger

# Tabela de governança (configurável via .env)
TABLE_ID_DATA_ACCESS = env.BQ_TABLE_ID_DATA_ACCESS
print(TABLE_ID_DATA_ACCESS)
# ========================================================================
# CONFIGURAÇÃO - EDITE AQUI
# ========================================================================

# CPF do super admin inicial (sem pontos ou traços)
# Este CPF deve corresponder ao campo 'preferred_username' do JWT após login gov.br
SUPER_ADMIN_CPF = "12345678900"  # Ex: "12345678900"

# Informações completas do super admin
SUPER_ADMIN_NAME = "ASD"
SUPER_ADMIN_EMAIL = "asd@asd.asd"  # Email do super admin
SUPER_ADMIN_OCUPACAO = "ASD"  # Ocupação/cargo
SUPER_ADMIN_SECRETARIA = "ASD"  # Secretaria/órgão

# ========================================================================
# VALIDAÇÕES
# ========================================================================


def validate_cpf(cpf: str) -> bool:
    """Valida formato básico do CPF"""
    if not cpf or len(cpf) != 11:
        return False
    if not cpf.isdigit():
        return False
    if cpf == "SUBSTITUA_PELO_SEU_CPF":
        return False
    return True


def table_exists() -> bool:
    """Verifica se a tabela data_access existe"""
    query = f"""
    SELECT COUNT(*) as count
    FROM `{env.BQ_PROJECT_ID}.{env.BQ_DATASET_ID}.INFORMATION_SCHEMA.TABLES`
    WHERE table_name = '{TABLE_ID_DATA_ACCESS}'
    """

    try:
        result = execute_query(query)
        # Polars DataFrame: usar row() ou item() ao invés de iloc
        return result.row(0)[0] > 0
    except Exception as e:
        logger.error(f"❌ Erro ao verificar existência da tabela: {e}")
        return False


def create_table():
    """Cria a tabela data_access se não existir"""
    print(f"📦 Criando tabela {TABLE_ID_DATA_ACCESS}...")

    query = f"""
    CREATE TABLE `{env.BQ_PROJECT_ID}.{env.BQ_DATASET_ID}.{TABLE_ID_DATA_ACCESS}` (
      cpf STRING NOT NULL,
      nome STRING,
      ocupacao STRING,
      secretaria STRING,
      email STRING,
      is_admin BOOLEAN NOT NULL,
      is_super_admin BOOLEAN NOT NULL,

      -- Tipo de permissão (preenchido pelo código: super_admin, admin, user)
      permission STRING NOT NULL,

      -- IDs autorizados com nomes (arrays de STRUCT)
      id_cras_list ARRAY<STRUCT<id STRING, nome STRING>>,
      id_escola_list ARRAY<STRUCT<id STRING, nome STRING>>,
      id_cre_list ARRAY<STRUCT<id STRING, nome STRING>>,
      id_ap_list ARRAY<STRUCT<id STRING, nome STRING>>,
      id_cas_list ARRAY<STRUCT<id STRING, nome STRING>>,
      id_clinica_familia_list ARRAY<STRUCT<id STRING, nome STRING>>,

      -- Auditoria
      created_by STRING NOT NULL,
      created_at TIMESTAMP NOT NULL,
      updated_by STRING,
      updated_at TIMESTAMP,

      -- Metadata
      active BOOLEAN NOT NULL,
      notes STRING
    )
    PARTITION BY DATE(created_at)
    CLUSTER BY cpf, active
    OPTIONS(
      description="Tabela de governança - controle de acesso por CPF"
    )
    """

    try:
        execute_query(query)
        print(f"✅ Tabela {TABLE_ID_DATA_ACCESS} criada com sucesso!\n")
        return True
    except Exception as e:
        print(f"❌ ERRO ao criar tabela: {e}\n")
        logger.error(f"❌ Erro ao criar tabela: {e}")
        return False


def check_super_admin_exists(cpf: str) -> bool:
    """Verifica se já existe um super admin com este CPF"""
    query = f"""
    SELECT COUNT(*) as count
    FROM `{env.BQ_PROJECT_ID}.{env.BQ_DATASET_ID}.{TABLE_ID_DATA_ACCESS}`
    WHERE cpf = '{cpf}' AND is_super_admin = TRUE AND active = TRUE
    """

    try:
        result = execute_query(query)
        # Polars DataFrame: usar row() ou item() ao invés de iloc
        return result.row(0)[0] > 0
    except Exception as e:
        logger.error(f"❌ Erro ao verificar super admin existente: {e}")
        return False


def update_super_admin(cpf: str):
    """Atualiza as informações de um super admin existente"""
    print(f"\n🔄 Atualizando informações do super admin {cpf}...")

    query = f"""
    UPDATE `{env.BQ_PROJECT_ID}.{env.BQ_DATASET_ID}.{TABLE_ID_DATA_ACCESS}`
    SET
        nome = '{SUPER_ADMIN_NAME}',
        ocupacao = '{SUPER_ADMIN_OCUPACAO}',
        secretaria = '{SUPER_ADMIN_SECRETARIA}',
        email = '{SUPER_ADMIN_EMAIL}',
        updated_by = 'SYSTEM_BOOTSTRAP',
        updated_at = CURRENT_TIMESTAMP(),
        notes = 'Super admin atualizado via bootstrap script - Acesso total ao sistema'
    WHERE cpf = '{cpf}' AND is_super_admin = TRUE AND active = TRUE
    """

    try:
        execute_query(query)
        print("✅ Informações do super admin atualizadas com sucesso!\n")
        return True
    except Exception as e:
        print(f"❌ ERRO ao atualizar super admin: {e}\n")
        logger.error(f"❌ Erro ao atualizar super admin: {e}")
        return False


def bootstrap_super_admin(skip_confirmation: bool = False):
    """Cria o super admin inicial"""

    print("\n" + "=" * 70)
    print("🚀 BOOTSTRAP DO SUPER ADMIN")
    print("=" * 70 + "\n")

    # Validar CPF
    if not validate_cpf(SUPER_ADMIN_CPF):
        print("❌ ERRO: CPF inválido!")
        print(f"   CPF fornecido: {SUPER_ADMIN_CPF}")
        print("\n📝 Instruções:")
        print("   1. Edite este script (bootstrap_super_admin.py)")
        print("   2. Substitua SUPER_ADMIN_CPF pelo seu CPF (11 dígitos, sem pontos)")
        print("   3. Execute o script novamente")
        print("\n   Exemplo: SUPER_ADMIN_CPF = '12345678900'\n")
        sys.exit(1)

    print(f"📋 CPF do super admin: {SUPER_ADMIN_CPF}")
    print(f"📋 Nome: {SUPER_ADMIN_NAME}")
    print(f"📋 Email: {SUPER_ADMIN_EMAIL}")
    print(f"📋 Ocupação: {SUPER_ADMIN_OCUPACAO}")
    print(f"📋 Secretaria: {SUPER_ADMIN_SECRETARIA}")
    print(f"📋 Projeto: {env.BQ_PROJECT_ID}")
    print(f"📋 Dataset: {env.BQ_DATASET_ID}")
    print(f"📋 Tabela: {TABLE_ID_DATA_ACCESS}\n")
    # Verificar se tabela existe, se não, criar
    if not table_exists():
        print(f"⚠️  Tabela {TABLE_ID_DATA_ACCESS} não existe. Criando...\n")
        if not create_table():
            print("❌ Não foi possível criar a tabela. Abortando.\n")
            sys.exit(1)
    else:
        print(f"✅ Tabela {TABLE_ID_DATA_ACCESS} já existe\n")

    # Verificar se já existe super admin
    if check_super_admin_exists(SUPER_ADMIN_CPF):
        print("⚠️  AVISO: Já existe um super admin ativo com este CPF!")
        print("   Você pode atualizar as informações dele com os dados configurados.\n")

        if not skip_confirmation:
            update_confirm = (
                input(
                    "Deseja atualizar as informações do super admin existente? [s/N]: "
                )
                .strip()
                .lower()
            )

            if update_confirm in ["s", "sim", "y", "yes"]:
                if update_super_admin(SUPER_ADMIN_CPF):
                    # Refresh cache de governança
                    try:
                        from src.utils.data_manager import DataManager
                        from src.api.v1.queries import GOVERNANCE_TABLE_QUERY

                        DataManager.get_dataset(
                            GOVERNANCE_TABLE_QUERY, bypass_cache=True
                        )
                        print("✅ Cache de governança atualizado\n")
                    except Exception as e:
                        print(f"⚠️  Aviso: Não foi possível atualizar cache: {e}")
                        print(
                            "   O cache será atualizado automaticamente na próxima request.\n"
                        )

                    print("=" * 70)
                    print("🎉 ATUALIZAÇÃO CONCLUÍDA")
                    print("=" * 70 + "\n")
                sys.exit(0)
            else:
                print("\n❌ Atualização cancelada. Nenhuma ação realizada.\n")
                sys.exit(0)
        else:
            print(
                "⚠️  Modo não-interativo: atualizando super admin sem confirmação...\n"
            )
            if update_super_admin(SUPER_ADMIN_CPF):
                # Refresh cache de governança
                try:
                    from src.utils.data_manager import DataManager
                    from src.api.v1.queries import GOVERNANCE_TABLE_QUERY

                    DataManager.get_dataset(GOVERNANCE_TABLE_QUERY, bypass_cache=True)
                    print("✅ Cache de governança atualizado\n")
                except Exception as e:
                    print(f"⚠️  Aviso: Não foi possível atualizar cache: {e}")
                    print(
                        "   O cache será atualizado automaticamente na próxima request.\n"
                    )

                print("=" * 70)
                print("🎉 ATUALIZAÇÃO CONCLUÍDA")
                print("=" * 70 + "\n")
            sys.exit(0)

    # Confirmar com usuário
    if not skip_confirmation:
        print(
            "⚠️  ATENÇÃO: Este script criará um super admin com ACESSO TOTAL ao sistema."
        )
        print("   O super admin poderá:")
        print("   - Ver TODOS os dados sem restrições")
        print("   - Criar e gerenciar outros admins")
        print("   - Atribuir qualquer ID a qualquer usuário\n")

        confirm = input("Deseja continuar? [s/N]: ").strip().lower()

        if confirm not in ["s", "sim", "y", "yes"]:
            print("\n❌ Operação cancelada pelo usuário.\n")
            sys.exit(0)
    else:
        print("⚠️  Modo não-interativo: criando super admin sem confirmação...\n")

    # Criar super admin
    print("\n🔄 Criando super admin...")

    query = f"""
    INSERT INTO `{env.BQ_PROJECT_ID}.{env.BQ_DATASET_ID}.{TABLE_ID_DATA_ACCESS}`
    (
        cpf,
        nome,
        ocupacao,
        secretaria,
        email,
        is_admin,
        is_super_admin,
        permission,
        id_cras_list,
        id_escola_list,
        id_cre_list,
        id_ap_list,
        id_cas_list,
        id_clinica_familia_list,
        created_by,
        created_at,
        updated_by,
        updated_at,
        active,
        notes
    )
    VALUES (
        '{SUPER_ADMIN_CPF}',
        '{SUPER_ADMIN_NAME}',
        '{SUPER_ADMIN_OCUPACAO}',
        '{SUPER_ADMIN_SECRETARIA}',
        '{SUPER_ADMIN_EMAIL}',
        TRUE,
        TRUE,
        'super_admin',
        [],  -- Super admin tem acesso total, não precisa de IDs específicos
        [],
        [],
        [],
        [],
        [],
        'SYSTEM_BOOTSTRAP',
        CURRENT_TIMESTAMP(),
        'SYSTEM_BOOTSTRAP',
        CURRENT_TIMESTAMP(),
        TRUE,
        'Super admin criado via bootstrap script - Acesso total ao sistema'
    )
    """

    try:
        execute_query(query)
        print("✅ Super admin criado com sucesso!\n")

        # Refresh cache de governança
        try:
            from src.utils.data_manager import DataManager
            from src.api.v1.queries import GOVERNANCE_TABLE_QUERY

            # Force refresh usando bypass_cache
            DataManager.get_dataset(GOVERNANCE_TABLE_QUERY, bypass_cache=True)
            print("✅ Cache de governança atualizado\n")
        except Exception as e:
            print(f"⚠️  Aviso: Não foi possível atualizar cache: {e}")
            print("   O cache será atualizado automaticamente na próxima request.\n")

        print("=" * 70)
        print("🎉 BOOTSTRAP CONCLUÍDO")
        print("=" * 70 + "\n")
        print("📝 Próximos passos:")
        print("   1. Faça login no sistema usando gov.br com o CPF configurado")
        print(f"      CPF: {SUPER_ADMIN_CPF}")
        print(f"      Nome: {SUPER_ADMIN_NAME}")
        print(f"      Email: {SUPER_ADMIN_EMAIL}")
        print("   2. Você deve ver o menu 'Admin' na interface")
        print("   3. Use o menu Admin para criar outros usuários e admins\n")
        print("⚠️  IMPORTANTE: Guarde este CPF em local seguro!")
        print("   Este é o único super admin do sistema.")
        print("\n💡 Para editar as informações do super admin:")
        print("   - Edite as variáveis no início deste script")
        print("   - Execute o script novamente (ele atualizará as informações)\n")

    except Exception as e:
        print(f"\n❌ ERRO ao criar super admin: {e}\n")
        logger.error(f"❌ Erro no bootstrap: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Bootstrap script para criar o primeiro super admin"
    )
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Pular confirmação (modo não-interativo)",
    )
    args = parser.parse_args()

    try:
        bootstrap_super_admin(skip_confirmation=args.yes)
    except KeyboardInterrupt:
        print("\n\n❌ Operação cancelada pelo usuário.\n")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Erro inesperado: {e}\n")
        logger.error(f"❌ Erro inesperado no bootstrap: {e}", exc_info=True)
        sys.exit(1)
