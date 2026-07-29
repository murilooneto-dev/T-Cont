_BANCOS_CONHECIDOS = [
    ("ITAU", "Itaú"),
    ("ITAÚ", "Itaú"),
    ("BRADESCO", "Bradesco"),
    ("BANCO DO BRASIL", "Banco do Brasil"),
    ("CAIXA ECONOMICA", "Caixa Econômica Federal"),
    ("CAIXA ECONÔMICA", "Caixa Econômica Federal"),
    ("SANTANDER", "Santander"),
    ("NUBANK", "Nubank"),
    ("INTER", "Inter"),
    ("SICOOB", "Sicoob"),
    ("SICREDI", "Sicredi"),
    ("C6 BANK", "C6 Bank"),
]


def extrair_banco(texto: str) -> str | None:
    texto_upper = texto.upper()
    for busca, exibicao in _BANCOS_CONHECIDOS:
        if busca in texto_upper:
            return exibicao
    return None
