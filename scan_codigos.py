"""
scan_codigos.py — Diagnóstico em campo: lista todos os instrumentos do
Sitrad e os códigos de valores que cada modelo expõe na API.

Uso (na raiz do projeto):  .venv\\Scripts\\python.exe scan_codigos.py
"""

from src import sitrad_client as s

linhas: list[str] = []


def out(texto: str) -> None:
    print(texto)
    linhas.append(texto)


for i in s.list_instruments():
    out("=" * 70)
    out(f"{i['id']} | {i.get('name')} | modelId={i.get('modelId')} | "
        f"model_name={i.get('model_name')} | status={i.get('status')}")
    try:
        vals = s.get_values(i["id"])
        if not vals:
            out("   (nenhum valor retornado)")
        for c, v in sorted(vals.items()):
            out(f"   {c:36s} = {v['value']} {v['unit']}")
    except Exception as exc:
        out(f"   ERRO ao consultar valores: {exc}")

out("=" * 70)
out("FIM DO SCAN")

with open("scan_resultado.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(linhas))
print("\nSalvo em scan_resultado.txt")
