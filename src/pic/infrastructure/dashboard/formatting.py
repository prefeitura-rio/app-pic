from src.pic.infrastructure.dashboard.config import MESES_LABELS


def _format_mes_label(mes: str) -> str:
    try:
        parts = mes.split("-")
        if len(parts) >= 2:
            ano = parts[0][2:]
            mes_num = parts[1]
            mes_nome = MESES_LABELS.get(mes_num, mes_num)
            return f"{mes_nome}/{ano}"
    except Exception:
        pass
    return mes
