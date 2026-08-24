"""Fase 0 — validação de endpoints e medição de cobertura.

Este módulo existe porque o código foi escrito sem acesso de rede às APIs
públicas brasileiras: o ambiente de desenvolvimento bloqueia todo host
``.gov.br``. Nada aqui pode ser tratado como confirmado até que este probe rode
num ambiente com acesso — o GitHub Actions.

O relatório responde quatro perguntas, em ordem de importância:

1. Os endpoints existem e devolvem o que a documentação promete?
2. O PNCP contém o pregão **presencial** de município pequeno? O caso-âncora
   (Nova Castilho, Pregão 007/2026, documentado de forma independente) é o teste.
   Se ele não aparecer, o cubo AUDESP do TCE-SP deixa de ser complemento e passa
   a ser obrigatório.
3. Qual a cobertura real por município, ano e modalidade?
4. Que tamanho tem o mercado de serviço técnico em saúde na região?
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from .config import DADOS, fontes, municipios as cfg_municipios
from .http import Cliente
from .ibge import Municipio, resolver
from .pncp import ClientePNCP, _aaaammdd, partes_controle_pncp
from .segmentar import Classificador
from .texto import apenas_digitos, normalizar

log = logging.getLogger("licita.probe")

RELATORIO = DADOS / "relatorio_cobertura.md"
BRUTO = DADOS / "probe.json"


@dataclass
class Sonda:
    nome: str
    url: str
    params: dict[str, Any] = field(default_factory=dict)
    status: int | None = None
    ok: bool = False
    registros: int | None = None
    campos: list[str] = field(default_factory=list)
    erro: str | None = None
    observacao: str = ""
    # Nem toda resposta não-ok é veredito sobre a fonte. Bloqueio por excesso de
    # requisições e timeout dizem que a pergunta não foi respondida, não que a
    # resposta é não. Confundir os dois foi o que fez o relatório de 24/08
    # publicar "nenhuma janela de datas aceita" quando só houvera 429.
    inconclusivo: bool = False

    @property
    def veredito(self) -> str:
        if self.ok and self.registros:
            return "OK"
        if self.ok:
            return "VAZIO"
        if self.inconclusivo:
            return "INCONCLUSIVO"
        return "FALHA"


def _campos_do_primeiro(dados: Any) -> tuple[int | None, list[str]]:
    """Extrai contagem e nomes de campo do primeiro registro, seja lista ou envelope."""
    if isinstance(dados, dict) and isinstance(dados.get("data"), list):
        registros = dados["data"]
    elif isinstance(dados, list):
        registros = dados
    else:
        return (None, sorted(dados)[:40] if isinstance(dados, dict) else [])
    if not registros:
        return (0, [])
    primeiro = registros[0]
    return (len(registros), sorted(primeiro)[:40] if isinstance(primeiro, dict) else [])


class Probe:
    def __init__(self) -> None:
        # Sondas de endpoint precisam bater na origem — cache aqui mascararia
        # justamente a falha que se quer detectar. As varreduras em massa, ao
        # contrário, usam cache: reexecutar o probe no mesmo dia fica barato.
        self.http = Cliente(usar_cache=False)
        self.http_massa = Cliente(usar_cache=True, perfil="http_massa")
        self.pncp = ClientePNCP(self.http_massa)
        self.sondas: list[Sonda] = []
        self.municipios: list[Municipio] = []
        self.ancora: dict[str, Any] = {}
        self.cobertura: list[dict] = []
        self.mercado_servico: list[dict] = []

    # ------------------------------------------------------------- endpoints

    def _sondar(self, nome: str, url: str, params: dict | None = None, obs: str = "") -> Sonda:
        resp = self.http.obter(url, params)
        registros, campos = _campos_do_primeiro(resp.dados)
        sonda = Sonda(
            nome=nome, url=url, params=params or {}, status=resp.status,
            ok=resp.ok, registros=registros, campos=campos,
            erro=resp.erro, observacao=obs,
        )
        self.sondas.append(sonda)
        log.info("[%s] %s -> %s", sonda.veredito, nome, resp.status)
        return sonda

    def sondar_endpoints(self) -> None:
        cfg = fontes()
        f_ibge, f_pncp = cfg["ibge"], cfg["pncp"]
        uf = cfg_municipios()["codigo_uf_ibge"]

        self._sondar(
            "IBGE · municípios da UF",
            f_ibge["base"] + f_ibge["municipios_por_uf"].format(uf=uf),
            obs="Resolve os códigos IBGE dos municípios-alvo.",
        )

        fim = date.today()
        inicio = fim - timedelta(days=cfg["pncp"]["janela_dias"])
        ancora = cfg_municipios()["caso_ancora"]

        self._sondar(
            "PNCP · contratações por publicação",
            f_pncp["consulta_base"] + f_pncp["contratacoes_publicacao"],
            {
                "dataInicial": _aaaammdd(inicio), "dataFinal": _aaaammdd(fim),
                "codigoModalidadeContratacao": 7, "uf": "SP",
                "pagina": 1, "tamanhoPagina": 10,
            },
            obs="Fundação do histórico. Modalidade 7 = pregão presencial.",
        )
        self._sondar(
            "PNCP · contratações com proposta aberta",
            f_pncp["consulta_base"] + f_pncp["contratacoes_proposta"],
            {
                "dataFinal": _aaaammdd(fim + timedelta(days=60)),
                "codigoModalidadeContratacao": 6, "uf": "SP",
                "pagina": 1, "tamanhoPagina": 10,
            },
            obs="Base do radar diário de oportunidades.",
        )
        self._sondar(
            "PNCP · atas de registro de preço",
            f_pncp["consulta_base"] + f_pncp["atas"],
            {
                "dataInicial": _aaaammdd(inicio), "dataFinal": _aaaammdd(fim),
                "pagina": 1, "tamanhoPagina": 10,
            },
        )
        self._sondar(
            "PNCP · contratos",
            f_pncp["consulta_base"] + f_pncp["contratos"],
            {
                "dataInicial": _aaaammdd(inicio), "dataFinal": _aaaammdd(fim),
                "pagina": 1, "tamanhoPagina": 10,
            },
            obs="Traz niFornecedor e valorGlobal: é a fonte de quem ganha o quê.",
        )

        # Rotas de detalhe: as menos confirmadas. Testadas contra o caso-âncora.
        cnpj = apenas_digitos(ancora["cnpj_orgao"])
        ano = ancora["ano"]
        seq = self.ancora.get("sequencial")
        if seq:
            self._sondar(
                "PNCP · itens da contratação",
                f_pncp["detalhe_base"] + f_pncp["itens"].format(cnpj=cnpj, ano=ano, sequencial=seq),
                obs="Caminho não confirmado em documentação oficial estável.",
            )
            self._sondar(
                "PNCP · resultados do item 1",
                f_pncp["detalhe_base"] + f_pncp["resultados"].format(
                    cnpj=cnpj, ano=ano, sequencial=seq, item=1),
                obs="Única via estruturada para vencedor e valor homologado por item.",
            )
            self._sondar(
                "PNCP · arquivos da contratação",
                f_pncp["detalhe_base"] + f_pncp["arquivos"].format(cnpj=cnpj, ano=ano, sequencial=seq),
                obs="Edital e ata em PDF; insumo do parser de contagem de licitantes.",
            )
        else:
            self.sondas.append(Sonda(
                nome="PNCP · rotas de detalhe (itens/resultados/arquivos)",
                url=f_pncp["detalhe_base"] + f_pncp["itens"],
                erro="não testadas: o caso-âncora não foi localizado na API de consulta",
                observacao="Sem o sequencial da contratação não há como montar a URL.",
            ))

    # ----------------------------------------------------------- caso-âncora

    def testar_caso_ancora(self) -> dict[str, Any]:
        """Procura no PNCP o Pregão Presencial 007/2026 de Nova Castilho.

        É o único ponto do projeto com verdade conhecida de forma independente
        (documentada no handoff a partir dos PDFs oficiais). Se o PNCP não o
        contiver, a base não serve para pregão presencial de município pequeno —
        que é justamente o padrão da região.
        """
        cfg = cfg_municipios()["caso_ancora"]
        cnpj = apenas_digitos(cfg["cnpj_orgao"])
        ano = cfg["ano"]
        alvo_numero = normalizar(cfg["numero_compra"])

        resultado: dict[str, Any] = {
            "procurado": {
                "municipio": cfg["municipio"], "cnpj_orgao": cnpj,
                "numero_compra": cfg["numero_compra"], "modalidade": cfg["modalidade"],
            },
            "encontrado": False,
            "verdade_conhecida": {
                "valor_unitario_estimado": cfg["valor_unitario_estimado"],
                "valor_unitario_homologado": cfg["valor_unitario_homologado"],
                "quantidade_total": cfg["quantidade_total"],
                "valor_total_ata": cfg["valor_total_ata"],
                "licitantes_presentes": cfg["licitantes_presentes"],
            },
        }

        ibge = self._ibge_ancora()
        if not ibge:
            resultado["erro"] = (
                f"{cfg['municipio']} não está entre os municípios-alvo, então o "
                "teste de aceitação não pôde ser executado. Acrescente-o a "
                "`municipios_extras` em config/municipios.yml."
            )
            self.ancora.update(resultado)
            return resultado

        # Varre o ano inteiro do caso, em todas as modalidades configuradas: o
        # município pode ter publicado sob modalidade diferente da esperada.
        for modalidade in fontes()["pncp"]["modalidades"]:
            achados = self.pncp.contratacoes_publicadas(
                ibge, modalidade, date(ano, 1, 1), date(ano, 12, 31)
            )
            for bruto in achados:
                numero = normalizar(bruto.get("numeroCompra"))
                objeto = normalizar(bruto.get("objetoCompra"))
                casa_numero = alvo_numero and alvo_numero in numero
                casa_objeto = cfg["objeto_contem"] in objeto
                if not (casa_numero or casa_objeto):
                    continue
                controle = bruto.get("numeroControlePNCP")
                partes = partes_controle_pncp(controle)
                resultado.update({
                    "encontrado": True,
                    "numero_controle_pncp": controle,
                    "modalidade_publicada": bruto.get("modalidadeId"),
                    "modalidade_nome": bruto.get("modalidadeNome"),
                    "numero_compra": bruto.get("numeroCompra"),
                    "objeto": bruto.get("objetoCompra"),
                    "valor_total_estimado": bruto.get("valorTotalEstimado"),
                    "valor_total_homologado": bruto.get("valorTotalHomologado"),
                    "casou_por": "numero" if casa_numero else "objeto",
                })
                if partes:
                    self.ancora["sequencial"] = partes[1]
                    resultado["sequencial"] = partes[1]
                self.ancora.update(resultado)
                return resultado

        self.ancora.update(resultado)
        return resultado

    def _ibge_ancora(self) -> str:
        """Código IBGE do município do caso-âncora, ou "" se ele não for alvo.

        Devolver "" silenciosamente fazia a consulta seguir com o filtro de
        município em branco e voltar vazia — o relatório então dizia "caso-âncora
        NÃO ENCONTRADO" quando na verdade ele nunca fora procurado. Um teste de
        aceitação que falha por não ter rodado é pior que não ter teste.
        """
        alvo = normalizar(cfg_municipios()["caso_ancora"]["municipio"])
        for m in self.municipios:
            if normalizar(m.nome) == alvo:
                return m.codigo_ibge
        return ""

    # ------------------------------------------------------------- cobertura

    def varrer(self, anos: int = 3) -> None:
        """Varredura única que alimenta a cobertura E a sondagem de mercado.

        Antes eram dois laços independentes sobre os mesmos municípios e as
        mesmas modalidades, cada um refazendo as requisições do outro — as
        modalidades de serviço técnico (8, 9 e 12) eram buscadas duas vezes,
        ~20% de trabalho jogado fora. Aqui cada contratação é buscada uma vez e
        lida por dois analisadores.
        """
        classificador = Classificador()
        modalidades = fontes()["pncp"]["modalidades"]
        de_servico = set(fontes().get("modalidades_servico_tecnico", [8, 9, 12]))
        hoje = date.today()

        for mun in self.municipios:
            for ano in range(hoje.year - anos + 1, hoje.year + 1):
                fim = min(date(ano, 12, 31), hoje)
                for modalidade in modalidades:
                    achados = self.pncp.contratacoes_publicadas(
                        mun.codigo_ibge, modalidade, date(ano, 1, 1), fim
                    )
                    if not achados:
                        continue

                    self.cobertura.append({
                        "municipio": mun.nome,
                        "codigo_ibge": mun.codigo_ibge,
                        "ano": ano,
                        "modalidade": modalidade,
                        "contratacoes": len(achados),
                        "valor_estimado": sum(
                            float(a.get("valorTotalEstimado") or 0) for a in achados
                        ),
                    })

                    if modalidade in de_servico:
                        self._classificar_mercado(mun, modalidade, achados, classificador)

    def _classificar_mercado(self, mun, modalidade, achados, classificador) -> None:
        """Separa, do que já foi buscado, o que é serviço técnico em saúde.

        Dimensiona a segunda linha de negócio antes de qualquer investimento
        nela: dispensa, inexigibilidade e credenciamento são por onde município
        pequeno compra serviço técnico.
        """
        for bruto in achados:
            objeto = bruto.get("objetoCompra") or ""
            cls = classificador.classificar(objeto=objeto)
            if cls.tipo != "servico" or cls.dominio != "saude":
                continue
            self.mercado_servico.append({
                "municipio": mun.nome,
                "modalidade": modalidade,
                "segmento": cls.segmento,
                "objeto": objeto[:200],
                "valor_estimado": bruto.get("valorTotalEstimado"),
                "data": bruto.get("dataPublicacaoPncp"),
            })

    def sondar_filtro_municipio(self) -> Sonda:
        """Descobre como filtrar contratações por município.

        A primeira execução da Fase 0 varreu 37 municípios e voltou com zero
        contratações em todos, enquanto as sondas com `uf=SP` traziam registros
        normalmente. Ou seja: `codigoMunicipioIbge` é aceito pela API mas não
        casa nada da forma como estava sendo enviado — 851 requisições gastas
        para não descobrir nada.

        Em vez de adivinhar a forma correta, esta sonda testa as variantes
        plausíveis contra um município que sabidamente compra (Jales, o maior da
        região) e relata qual devolve dados. O resultado orienta `pncp.py`.
        """
        cfg = fontes()["pncp"]
        url = cfg["consulta_base"] + cfg["contratacoes_publicacao"]
        fim = date.today()
        ini = fim - timedelta(days=cfg["janela_dias"] - 1)

        alvo = next(
            (m for m in self.municipios if normalizar(m.nome) == "jales"),
            self.municipios[0] if self.municipios else None,
        )
        if alvo is None:
            sonda = Sonda(nome="PNCP · filtro por município", url=url,
                          erro="nenhum município resolvido para testar")
            self.sondas.append(sonda)
            return sonda

        base = {
            "dataInicial": _aaaammdd(ini), "dataFinal": _aaaammdd(fim),
            "codigoModalidadeContratacao": 6, "pagina": 1, "tamanhoPagina": 10,
        }
        variantes = {
            "codigoMunicipioIbge só": {**base, "codigoMunicipioIbge": alvo.codigo_ibge},
            "codigoMunicipioIbge + uf": {**base, "codigoMunicipioIbge": alvo.codigo_ibge, "uf": alvo.uf},
            "codigoMunicipioIbge como int": {**base, "codigoMunicipioIbge": int(alvo.codigo_ibge)},
            "codigoUnidadeAdministrativa": {**base, "codigoUnidadeAdministrativa": alvo.codigo_ibge},
            "uf só (controle)": {**base, "uf": alvo.uf},
        }

        achados: dict[str, str] = {}
        vencedora = ""
        for rotulo, params in variantes.items():
            resp = self.http_massa.obter(url, params)
            n, _campos = _campos_do_primeiro(resp.dados)
            achados[rotulo] = f"HTTP {resp.status} · {n if n is not None else '—'} registros"
            if resp.ok and n:
                # "uf só" traz o estado inteiro; não serve como filtro de município.
                if not vencedora and rotulo != "uf só (controle)":
                    vencedora = rotulo

        detalhe = " | ".join(f"{k}: {v}" for k, v in achados.items())
        sonda = Sonda(
            nome=f"PNCP · filtro por município (testado em {alvo.nome})",
            url=url, status=200, ok=bool(vencedora),
            registros=1 if vencedora else 0,
            erro=None if vencedora else f"nenhuma variante filtrou por município. {detalhe}",
            observacao=(
                f"Variante que funciona: **{vencedora}**. {detalhe}" if vencedora
                else "Sem forma conhecida de filtrar por município: a coleta terá "
                     "de buscar por UF e filtrar localmente pelo código IBGE da "
                     "unidade do órgão. " + detalhe
            ),
        )
        self.sondas.append(sonda)
        return sonda

    def descobrir_tamanho_pagina(self) -> Sonda:
        """Descobre o maior `tamanhoPagina` que a API aceita.

        A primeira varredura real usou 500 (valor que a documentação dá como
        máximo) e voltou vazia nos 37 municípios, enquanto as sondas — que usam
        10 — traziam registros. Como a API responde 422 a parâmetro inválido,
        um `tamanhoPagina` recusado explica as 851 requisições sem resultado.
        Descobrir o teto real vale mais que confiar no número documentado.
        """
        cfg = fontes()["pncp"]
        url = cfg["consulta_base"] + cfg["contratacoes_publicacao"]
        fim = date.today()
        ini = fim - timedelta(days=89)
        tentados: dict[int, str] = {}
        bloqueados: list[int] = []
        maior = 0

        for tamanho in (10, 50, 100, 500):
            resp = self.http_massa.obter(url, {
                "dataInicial": _aaaammdd(ini), "dataFinal": _aaaammdd(fim),
                "codigoModalidadeContratacao": 6, "uf": "SP",
                "pagina": 1, "tamanhoPagina": tamanho,
            })
            n, _ = _campos_do_primeiro(resp.dados)
            tentados[tamanho] = f"HTTP {resp.status}·{n if n is not None else '—'}"
            # Aceito é qualquer resposta 2xx: página válida e vazia é resposta da
            # API, não recusa do parâmetro. Exigir `n` truthy confundia período
            # sem contratação com tamanhoPagina rejeitado.
            if resp.ok or resp.status == 204:
                maior = tamanho
            elif resp.status in (None, 429):
                bloqueados.append(tamanho)

        detalhe = " | ".join(f"{k}: {v}" for k, v in tentados.items())
        sonda = Sonda(
            nome="PNCP · maior tamanhoPagina aceito",
            url=url, status=200, ok=bool(maior), registros=maior,
            inconclusivo=bool(bloqueados) and not maior,
            erro=None if maior else f"nenhum tamanho aceito. {detalhe}",
            observacao=(
                f"Maior aceito: **{maior}**. `tamanho_pagina` está em "
                f"{cfg['tamanho_pagina']}. {detalhe}"
                + (f" Sem veredito para {bloqueados}: bloqueio ou timeout, não recusa."
                   if bloqueados else "")
                if maior else detalhe
            ),
        )
        self.sondas.append(sonda)
        return sonda

    def descobrir_tamanho_pagina_itens(self) -> Sonda:
        """Descobre o maior `tamanhoPagina` que `/itens` aceita.

        `/itens` é a API de detalhe, não a de consulta — não há garantia de que
        o mesmo teto medido em `descobrir_tamanho_pagina` valha aqui. O alvo é o
        SRP `45138070000149-1-000762/2026` (Pregão Eletrônico 11/2026, Santa Fé
        do Sul), a mesma contratação que a coleta sem paginação truncava em 10
        itens — se ela devolver mais de 10 com paginação, a correção funcionou;
        o valor de `tentados` diz até onde o `tamanhoPagina` foi aceito.
        """
        cfg = fontes()["pncp"]
        cnpj, ano, sequencial = "45138070000149", 2026, "762"
        url = cfg["detalhe_base"] + cfg["itens"].format(
            cnpj=cnpj, ano=ano, sequencial=sequencial
        )
        tentados: dict[int, str] = {}
        bloqueados: list[int] = []
        maior = 0
        maior_contagem = 0

        for tamanho in (10, 50, 100, 500):
            resp = self.http_massa.obter(url, {"pagina": 1, "tamanhoPagina": tamanho})
            n, _ = _campos_do_primeiro(resp.dados)
            tentados[tamanho] = f"HTTP {resp.status}·{n if n is not None else '—'}"
            if resp.ok or resp.status == 204:
                maior = tamanho
                maior_contagem = max(maior_contagem, n or 0)
            elif resp.status in (None, 429):
                bloqueados.append(tamanho)

        detalhe = " | ".join(f"{k}: {v}" for k, v in tentados.items())
        sonda = Sonda(
            nome="PNCP · maior tamanhoPagina aceito em /itens",
            url=url, status=200, ok=bool(maior), registros=maior_contagem,
            inconclusivo=bool(bloqueados) and not maior,
            erro=None if maior else f"nenhum tamanho aceito. {detalhe}",
            observacao=(
                f"Maior aceito: **{maior}**, {maior_contagem} itens devolvidos no SRP "
                f"de referência. `pncp.tamanho_pagina.itens` está em "
                f"{cfg['tamanho_pagina'].get('itens')}. {detalhe}"
                + (f" Sem veredito para {bloqueados}: bloqueio ou timeout, não recusa."
                   if bloqueados else "")
                if maior else detalhe
            ),
        )
        self.sondas.append(sonda)
        return sonda

    def descobrir_janela(self) -> Sonda:
        """Descobre o maior intervalo de datas que a API aceita numa requisição.

        `fontes.yml` fixa 90 dias por precaução, valor escolhido sem evidência.
        Se a API aceitar um ano, a varredura inteira cai a um quarto das
        requisições. Saber esse limite é resultado da Fase 0, não detalhe de
        implementação — por isso vira uma sonda no relatório.
        """
        cfg = fontes()["pncp"]
        url = cfg["consulta_base"] + cfg["contratacoes_publicacao"]
        fim = date.today()
        aceitos: list[int] = []
        bloqueados: list[int] = []
        tentados: dict[int, str] = {}

        for dias in (90, 180, 365):
            resp = self.http_massa.obter(url, {
                "dataInicial": _aaaammdd(fim - timedelta(days=dias - 1)),
                "dataFinal": _aaaammdd(fim),
                "codigoModalidadeContratacao": 6,
                "uf": "SP", "pagina": 1, "tamanhoPagina": 10,
            })
            tentados[dias] = f"HTTP {resp.status if resp.status is not None else 'sem resposta'}"
            if resp.ok or resp.status == 204:
                aceitos.append(dias)
            elif resp.status in (400, 422):
                # Recusa de verdade: a API avaliou o parâmetro e disse não.
                # Janelas maiores também serão recusadas, então para aqui.
                break
            else:
                # 429, 5xx ou timeout: a pergunta não foi respondida. Segue
                # tentando as outras janelas em vez de declarar recusa.
                bloqueados.append(dias)

        maior = max(aceitos) if aceitos else 0
        detalhe = " | ".join(f"{k}d: {v}" for k, v in tentados.items())
        sonda = Sonda(
            nome="PNCP · maior janela de datas aceita",
            url=url, status=200 if maior else None, ok=bool(maior),
            registros=maior,
            inconclusivo=bool(bloqueados) and not maior,
            observacao=(
                f"A API aceitou janela de {maior} dias. `janela_dias` está em "
                f"{cfg['janela_dias']}; ajustar reduz as requisições na proporção. "
                + detalhe
                if maior else
                (f"Sem veredito: as janelas {bloqueados} não foram avaliadas pela API "
                 f"(bloqueio ou timeout). {detalhe}" if bloqueados else
                 f"A API recusou a menor janela testada. {detalhe}")
            ),
        )
        self.sondas.append(sonda)
        return sonda

    def medir_ritmo(self) -> Sonda:
        """Mede a pausa entre chamadas que o PNCP sustenta sem devolver 429.

        Nem o Manual das APIs de Consultas nem o Manual de Integração do PNCP
        documentam limite de requisições — mas a API devolve
        "Limite de requisições excedido" com status 429, e a varredura de
        2026-08-24 tomou 103 delas usando pausa de 0,35s. Sem número documentado,
        a saída é medir: séries curtas com pausas decrescentes, relatando em qual
        delas o bloqueio começa. `pausa_entre_chamadas_s` sai de chute e vira
        valor medido, como já acontece com `tamanhoPagina`.

        Usa cliente próprio, sem cache: cache aqui mediria o disco, não a API.
        """
        cfg = fontes()["pncp"]
        url = cfg["consulta_base"] + cfg["contratacoes_publicacao"]
        fim = date.today()
        por_serie = 8
        resultados: dict[float, str] = {}
        sustentavel: float | None = None

        for pausa in (2.0, 1.0, 0.5, 0.25):
            sonda_http = Cliente(usar_cache=False, perfil="http_massa")
            # Piso e teto no mesmo valor: trava o ritmo para que o freio
            # adaptativo não interfira na medição.
            sonda_http.pausa = pausa
            sonda_http.pausa_teto = pausa
            sonda_http._pausa_atual = pausa

            excessos = outras = 0
            for i in range(por_serie):
                # Janela distinta a cada chamada: evita que um proxy responda de
                # cache e a série meça a rede em vez do limite do servidor.
                resp = sonda_http.obter(url, {
                    "dataInicial": _aaaammdd(fim - timedelta(days=30 + i)),
                    "dataFinal": _aaaammdd(fim - timedelta(days=i)),
                    "codigoModalidadeContratacao": 6,
                    "uf": "SP", "pagina": 1, "tamanhoPagina": 10,
                })
                if resp.status == 429:
                    excessos += 1
                elif not (resp.ok or resp.status == 204):
                    outras += 1

            resultados[pausa] = (
                f"{por_serie - excessos - outras}/{por_serie} ok"
                + (f", {excessos}x429" if excessos else "")
                + (f", {outras} outras falhas" if outras else "")
            )
            if excessos == 0 and sustentavel is None:
                sustentavel = pausa
            if excessos:
                # A partir daqui só piora; poupa requisições e poupa o servidor.
                break

        detalhe = " | ".join(f"pausa {k}s: {v}" for k, v in resultados.items())
        atual = fontes()["http_massa"]["pausa_entre_chamadas_s"]
        sonda = Sonda(
            nome="PNCP · ritmo sustentável (pausa entre chamadas)",
            url=url, status=200, ok=sustentavel is not None,
            registros=int((sustentavel or 0) * 1000),
            inconclusivo=sustentavel is None,
            erro=None if sustentavel is not None else f"toda série tomou 429. {detalhe}",
            observacao=(
                f"Menor pausa sem 429 nesta medição: **{sustentavel}s**. "
                f"`http_massa.pausa_entre_chamadas_s` está em {atual}s. {detalhe}"
                if sustentavel is not None else
                f"Nenhuma pausa testada ficou livre de 429. {detalhe}"
            ),
        )
        self.sondas.append(sonda)
        return sonda

    # ------------------------------------------------------------- execução

    def executar(self, anos: int = 3, completo: bool = True) -> None:
        self.municipios = resolver(self.http, forcar=True)
        log.info("municípios-alvo resolvidos: %d", len(self.municipios))
        self.testar_caso_ancora()
        self.sondar_endpoints()
        self.sondar_filtro_municipio()
        self.descobrir_tamanho_pagina()
        self.descobrir_tamanho_pagina_itens()
        self.descobrir_janela()
        self.medir_ritmo()
        if completo:
            self.varrer(anos=anos)

    # ------------------------------------------------------------ relatório

    def escrever(self) -> None:
        DADOS.mkdir(parents=True, exist_ok=True)
        BRUTO.write_text(
            json.dumps(
                {
                    "sondas": [vars(s) for s in self.sondas],
                    "caso_ancora": self.ancora,
                    "cobertura": self.cobertura,
                    "mercado_servico": self.mercado_servico,
                    "municipios": [vars(m) for m in self.municipios],
                    "falhas_coleta": [vars(f) for f in self.pncp.falhas],
                },
                ensure_ascii=False, indent=2, default=str,
            ) + "\n",
            encoding="utf-8",
        )
        RELATORIO.write_text(self._markdown(), encoding="utf-8")
        log.info("relatório escrito em %s", RELATORIO)

    def _markdown(self) -> str:
        from .relatorio import montar
        return montar(self)
