"""Interface de linha de comando.

    python -m licita probe        # Fase 0 — valida fontes e mede cobertura
    python -m licita municipios   # resolve e grava os municípios-alvo
    python -m licita historico    # backfill de contratações + itens + resultados
    python -m licita radar        # varredura rápida de propostas em aberto
    python -m licita atas         # atas de registro de preço e contratos
    python -m licita metricas     # recalcula o Índice de Oportunidade
    python -m licita exportar     # CSV, XLSX e painel HTML
    python -m licita tudo         # histórico + atas + métricas + exports
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date

from .coleta import Coletor
from .config import DADOS
from .db import ARQUIVO_PADRAO, Base
from .exportar import para_csv, para_painel, para_xlsx
from .ibge import resolver
from .metricas import calcular
from .probe import Probe
from .config import fontes


def _log(verboso: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verboso else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s · %(message)s",
        datefmt="%H:%M:%S",
    )


def _periodo(args: argparse.Namespace) -> tuple[date, date]:
    hoje = date.today()
    if args.desde:
        inicio = date.fromisoformat(args.desde)
    else:
        anos = args.anos or fontes()["coleta"]["anos_historico"]
        inicio = date(hoje.year - anos + 1, 1, 1)
    fim = date.fromisoformat(args.ate) if args.ate else hoje
    return inicio, fim


def _alvos(base: Base, forcar: bool = False):
    alvos = resolver(forcar=forcar)
    Coletor(base).gravar_municipios(alvos)
    return alvos


def cmd_probe(args: argparse.Namespace) -> int:
    probe = Probe()
    probe.executar(anos=args.anos or 3, completo=not args.rapido)
    probe.escrever()

    falhas = [s for s in probe.sondas if not s.ok]
    achou = probe.ancora.get("encontrado")

    print()
    print(f"Municípios-alvo ....... {len(probe.municipios)}")
    print(f"Endpoints OK .......... {len(probe.sondas) - len(falhas)}/{len(probe.sondas)}")
    print(f"Caso-âncora ........... {'ENCONTRADO' if achou else 'NÃO ENCONTRADO'}")
    print(f"Cobertura ............. {len(probe.cobertura)} combinações município/ano/modalidade")
    print(f"Serviço técnico saúde . {len(probe.mercado_servico)} contratações")
    print(f"\nRelatório: {DADOS / 'relatorio_cobertura.md'}")

    # Endpoint quebrado é falha de execução: o CI precisa acusar em vermelho.
    return 1 if falhas else 0


def cmd_municipios(args: argparse.Namespace) -> int:
    with Base(args.base) as base:
        alvos = _alvos(base, forcar=True)
        for m in alvos:
            marca = "*" if m.prioritario else " "
            print(f" {marca} {m.codigo_ibge}  {m.nome:<28} {m.regiao_imediata}")
        print(f"\n{len(alvos)} municípios · (*) prioritários")
    return 0


def cmd_historico(args: argparse.Namespace) -> int:
    inicio, fim = _periodo(args)
    with Base(args.base) as base:
        alvos = _alvos(base)
        coletor = Coletor(base)
        print(f"Coletando {inicio} a {fim} em {len(alvos)} municípios...")
        resumo = coletor.coletar_historico(alvos, inicio, fim, com_detalhe=not args.sem_detalhe)
        coletor.atualizar_cobertura()
        print(resumo)
        if resumo.sem_detalhe:
            print(f"Sem detalhe de itens: {len(resumo.sem_detalhe)} contratações")
    return 0


def cmd_radar(args: argparse.Namespace) -> int:
    with Base(args.base) as base:
        alvos = _alvos(base)
        coletor = Coletor(base)
        print(coletor.coletar_radar(alvos, args.horizonte))
    return 0


def cmd_atas(args: argparse.Namespace) -> int:
    inicio, fim = _periodo(args)
    with Base(args.base) as base:
        alvos = _alvos(base)
        print(Coletor(base).coletar_atas_e_contratos(alvos, inicio, fim))
    return 0


def cmd_metricas(args: argparse.Namespace) -> int:
    with Base(args.base) as base:
        print(f"{calcular(base)} linhas de métrica calculadas")
        topo = base.consultar(
            """
            SELECT mu.nome, m.segmento, m.ano, m.indice_oportunidade, m.itens_desertos,
                   m.desagio_medio, m.valor_estimado
              FROM metrica_mun_seg_ano m
              JOIN municipio mu ON mu.codigo_ibge = m.codigo_ibge
             WHERE m.indice_oportunidade IS NOT NULL
             ORDER BY m.indice_oportunidade DESC, m.valor_estimado DESC
             LIMIT 15
            """
        )
        if topo:
            print("\nMaior vácuo competitivo:\n")
            print(f"  {'Município':<20} {'Segmento':<26} {'Ano':<5} {'Índice':>7} {'Desertos':>9}")
            for l in topo:
                print(f"  {l['nome'][:20]:<20} {l['segmento'][:26]:<26} {l['ano']:<5} "
                      f"{l['indice_oportunidade']:>7.1f} {l['itens_desertos']:>9}")
    return 0


def cmd_exportar(args: argparse.Namespace) -> int:
    with Base(args.base) as base:
        para_csv(base)
        para_xlsx(base)
        painel = para_painel(base)
        print(f"Exports em {DADOS}\nPainel: {painel}")
    return 0


def cmd_tudo(args: argparse.Namespace) -> int:
    for etapa in (cmd_historico, cmd_atas, cmd_metricas, cmd_exportar):
        codigo = etapa(args)
        if codigo:
            return codigo
    return 0


COMANDOS = {
    "probe": cmd_probe, "municipios": cmd_municipios, "historico": cmd_historico,
    "radar": cmd_radar, "atas": cmd_atas, "metricas": cmd_metricas,
    "exportar": cmd_exportar, "tudo": cmd_tudo,
}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="licita", description="Base de pesquisa de licitações da microrregião de Jales/SP"
    )
    p.add_argument("comando", choices=sorted(COMANDOS))
    p.add_argument("--base", default=str(ARQUIVO_PADRAO), help="caminho do arquivo SQLite")
    p.add_argument("--anos", type=int, help="quantos anos para trás coletar")
    p.add_argument("--desde", help="data inicial AAAA-MM-DD (tem precedência sobre --anos)")
    p.add_argument("--ate", help="data final AAAA-MM-DD")
    p.add_argument("--horizonte", type=int, help="dias à frente na varredura do radar")
    p.add_argument("--sem-detalhe", action="store_true",
                   help="não buscar itens e resultados (varredura rápida)")
    p.add_argument("--rapido", action="store_true",
                   help="probe: só endpoints e caso-âncora, sem medir cobertura")
    p.add_argument("-v", "--verboso", action="store_true")
    args = p.parse_args(argv)

    _log(args.verboso)
    try:
        return COMANDOS[args.comando](args)
    except KeyboardInterrupt:
        print("\ninterrompido", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
