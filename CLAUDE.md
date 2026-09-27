# CLAUDE.md

Orientação para o Claude Code (e qualquer agente de IA) que trabalhe neste
repositório. **Leia antes de qualquer tarefa.**

## O projeto

Porte do mestrado de Caio Lima (UFABC) para ROS 2 Lyrical + Gazebo Jetty em
Docker: captura de sEMG, classificadores, simulador do braço, painel no
navegador. É a base de simulação do projeto pessoal `semg-digital-twins`
(repositório privado `Calima94/semg-digital-twins`), cujas ADRs governam também
este repositório no que diz respeito a IA e integridade científica.

Onde está cada coisa: [README.md](README.md) (estado e estrutura),
[docs/COMO_RODAR.md](docs/COMO_RODAR.md), [docs/DECISOES.md](docs/DECISOES.md)
(decisões D1…), [docs/INVENTARIO_MESTRADO.md](docs/INVENTARIO_MESTRADO.md)
(achados no código original).

## Conformidade com o CNPq (Portaria nº 2.664/2026) — regras duras

O `semg-digital-twins` adota a **Portaria CNPq nº 2.664/2026** (Política de
Integridade na Atividade Científica, publicada em 11/03/2026; anúncio oficial:
<https://www.gov.br/cnpq/pt-br/assuntos/noticias/cnpq-em-acao/cnpq-publica-portaria-que-institui-politica-de-integridade-na-atividade-cientifica>)
como regra vinculante, na sua ADR-003. Este repositório segue a mesma regra
(decisão D28). Descumprir pode levar a advertência, suspensão de bolsa,
impedimento em seleções do CNPq, revogação de fomento e devolução de recursos.
**Não é zona cinza para arriscar: na dúvida, pare e pergunte ao Caio.**

**Obrigatório**

- **Declarar todo uso de IA**: a ferramenta ("Claude, da Anthropic, via Claude
  Code"), a fase da pesquisa e a finalidade. A declaração do repositório fica
  na seção "Uso de IA" do README; mantenha-a em dia quando o uso mudar.
- **Commits** com `Co-Authored-By` do Claude. **PRs** com o label
  `agent:claude-code`.
- **Documentação escrita predominantemente por IA** leva rodapé dizendo isso.
- **Revisão humana**: nada deste repositório vira artigo, relatório,
  dissertação, pôster ou qualquer entrega formal sem o Caio ler e editar. A
  responsabilidade pelo conteúdo final é integralmente dele, inclusive por
  erros da ferramenta.
- Mudanças de regra (este arquivo, decisões de governança) entram por PR que
  **o Caio aprova e integra**; não ligar auto-merge nesses PRs.

**Vedado**

- **Apresentar conteúdo gerado por IA como de autoria humana**, ou omitir o
  uso de IA em qualquer entrega.
- **Inventar referências.** Todo artigo, DOI, dataset ou URL citado precisa de
  link verificável (confira o DOI, por exemplo no Crossref). Se não der para
  verificar, marque "não confirmado" e peça aprovação do Caio antes de gravar.
- **Inventar dados.** Nenhum número, tabela ou métrica sem origem real e
  reproduzível (comando, semente e versão dos dados). Se faltam dados, diga que
  faltam.
- **Escrever pareceres de revisor** no lugar do Caio.

## Integridade científica (quando rodar experimentos)

Regras do `AGENTS.md` do `semg-digital-twins`, obrigatórias sempre que um
experimento roda de fato:

- **Sem vazamento de dados**: dividir treino/teste **antes** de qualquer
  estatística global; normalização, seleção de canais e redução de dimensão
  ajustadas só no treino.
- **Divisão por sujeito** quando a pergunta é generalizar entre pessoas
  (validação "participante novo" / LOSO), com a dispersão entre sujeitos.
- **Nada do alvo na construção de features** (nem janelamento, nem filtragem,
  nem seleção de canais olhando o alvo no conjunto inteiro).
- **Sementes fixas e registradas** na saída de todo experimento.
- **Resultados históricos do mestrado** (LDA/GNB/SVM/kNN/árvore sobre MAV/RMS)
  são referência: mudar o que os reproduz exige decisão registrada.
- **Reproduções fiéis** (ex.: a LSTM da disciplina, D26) copiam o original
  inclusive no que parece errado; as diferenças ficam declaradas.

## Fluxo de trabalho

- Código no WSL (`/home/caio/Consolida-o_Projetos_de_mestrado`); commit no WSL,
  push pelo git do Windows (a credencial do WSL trava).
- Branches `claude/<assunto>`; nunca commitar direto na `main` (ela exige os
  dois jobs do CI).
- Antes do commit: `scripts/ci_local.sh` (ou `--rapido`). Arquivos editados
  pelo Windows perdem o bit de execução: `chmod +x` nos scripts.
- Tudo o que o usuário usa ganha botão no painel (`scripts/painel.py`), não só
  comando.

---

*Redigido por Claude (Anthropic), via Claude Code, a pedido do Caio, a partir
da ADR-003 e do `AGENTS.md` do `semg-digital-twins`. Aprovação: Caio Lima, pelo
merge do PR.*
