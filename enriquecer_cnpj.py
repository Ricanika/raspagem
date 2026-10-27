"""Enriquece parceiros do Sankhya (sem e-mail/telefone) com dados públicos da Receita Federal.

Uso: python enriquecer_cnpj.py entrada.csv saida.csv
Entrada: CSV ';' com colunas codparc, nome_sankhya, cnpj, tipo.
Fonte: ReceitaWS (limite gratuito de 3 consultas/min) com fallback para publica.cnpj.ws.
"""
import csv
import json
import re
import sys
import time
import urllib.request

INTERVALO = 21  # segundos entre consultas, para respeitar o limite da ReceitaWS


def baixar(url):
    req = urllib.request.Request(url, headers={"User-Agent": "raspagem/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def via_receitaws(cnpj):
    d = baixar(f"https://receitaws.com.br/v1/cnpj/{cnpj}")
    if d.get("status") == "ERROR":
        raise ValueError(d.get("message"))
    socios = " | ".join(f"{s['nome']} ({s['qual'].split('-')[-1].strip()})" for s in d.get("qsa", []))
    return {
        "razao_social": d.get("nome", ""),
        "nome_fantasia": d.get("fantasia", ""),
        "situacao_receita": d.get("situacao", ""),
        "contato_socios": socios,
        "email": (d.get("email") or "").lower(),
        "telefone": d.get("telefone", ""),
        "logradouro": d.get("logradouro", ""),
        "numero": d.get("numero", ""),
        "complemento": d.get("complemento", ""),
        "bairro": d.get("bairro", ""),
        "municipio": d.get("municipio", ""),
        "uf": d.get("uf", ""),
        "cep": d.get("cep", ""),
        "fonte": "ReceitaWS",
    }


def via_cnpjws(cnpj):
    d = baixar(f"https://publica.cnpj.ws/cnpj/{cnpj}")
    e = d["estabelecimento"]
    tels = [f"({e[f'ddd{i}']}) {e[f'telefone{i}']}" for i in (1, 2) if e.get(f"telefone{i}")]
    socios = " | ".join(f"{s['nome']} ({s['qualificacao_socio']['descricao']})" for s in d.get("socios", []))
    return {
        "razao_social": d.get("razao_social", ""),
        "nome_fantasia": e.get("nome_fantasia") or "",
        "situacao_receita": e.get("situacao_cadastral", ""),
        "contato_socios": socios,
        "email": (e.get("email") or "").lower(),
        "telefone": " / ".join(tels),
        "logradouro": f"{e.get('tipo_logradouro') or ''} {e.get('logradouro') or ''}".strip(),
        "numero": e.get("numero") or "",
        "complemento": e.get("complemento") or "",
        "bairro": e.get("bairro") or "",
        "municipio": (e.get("cidade") or {}).get("nome", ""),
        "uf": (e.get("estado") or {}).get("sigla", ""),
        "cep": e.get("cep") or "",
        "fonte": "CNPJ.ws",
    }


def limpar_email(texto):
    achado = re.search(r"[\w.+-]+@[\w-]+(\.[\w-]+)+", texto or "")
    return achado.group(0).lower() if achado else ""


def limpar_telefone(texto):
    return " / ".join(dict.fromkeys(t.strip() for t in (texto or "").split("/") if t.strip()))


def consultar(cnpj):
    for fonte in (via_receitaws, via_cnpjws):
        try:
            return fonte(cnpj)
        except Exception as erro:  # tenta a próxima fonte
            print(f"  {fonte.__name__} falhou para {cnpj}: {erro}", file=sys.stderr)
    return {"fonte": "não encontrado"}


def main(entrada, saida):
    with open(entrada, encoding="utf-8") as f:
        parceiros = list(csv.DictReader(f, delimiter=";"))

    linhas = []
    for i, p in enumerate(parceiros):
        if i:
            time.sleep(INTERVALO)
        cnpj = p["cnpj"].zfill(14)
        print(f"[{i + 1}/{len(parceiros)}] {cnpj} {p['nome_sankhya']}", file=sys.stderr)
        dados = consultar(cnpj)
        cnpj_fmt = f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"
        endereco = ", ".join(x for x in (dados.get("logradouro"), dados.get("numero"), dados.get("complemento")) if x)
        endereco += f" - {dados.get('bairro', '')} - {dados.get('municipio', '')}/{dados.get('uf', '')} - CEP {dados.get('cep', '')}"
        linhas.append({
            "codparc": p["codparc"],
            "cnpj": cnpj_fmt,
            "razao_social": dados.get("razao_social") or p["nome_sankhya"],
            "nome_fantasia": dados.get("nome_fantasia", ""),
            "tipo_parceiro": p["tipo"],
            "situacao_receita": dados.get("situacao_receita", ""),
            "contato_socios": dados.get("contato_socios", ""),
            "email": limpar_email(dados.get("email")),
            "telefone": limpar_telefone(dados.get("telefone")),
            "endereco_completo": endereco,
            "fonte": dados.get("fonte", ""),
        })

    with open(saida, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(linhas[0]), delimiter=";")
        w.writeheader()
        w.writerows(linhas)
    print(f"Gerado {saida} com {len(linhas)} linhas", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
