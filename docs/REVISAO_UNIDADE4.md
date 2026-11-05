# Correspondência com a Unidade 4

Revisão de 5 de novembro de 2026. Base: material didático de Projeto e Análise
de Algoritmos da Universidade de Vila Velha, Unidade 4, 11 páginas, e enunciado
da atividade investigativa do TSP. As referências de seção abaixo são do PDF.

## Requisitos e evidências

| Requisito | Implementação e evidência | Situação |
|---|---|---|
| Cidades e custos (4.1) | gerar_cidades e matriz_de_custos, em tsp_forca_bruta.py; matriz salva por coleta | Atendido |
| Fixar v1 (4.1.2) | tsp_forca_bruta(d, fixar_inicio=True) fixa índice 0 | Atendido |
| Enumerar (n−1)! (4.1.3) | permutacoes faz enumeração completa, sem poda ou eliminação da rota inversa | Atendido |
| Avaliar n arestas (4.1.4) | custo_da_rota percorre n posições, fecha ciclo e incrementa contador por soma | Atendido |
| T(n)=Θ(n!) (4.1.5 e 4.1.8) | n·(n−1)! somas; contadores reais e assertivas | Atendido |
| Vários n, tempos reais | Coleta principal 3..10, três repetições; complementar com 10..12 | Atendido |
| Gráfico medido e c·n! | Figura linear e logarítmica; c por mínimos quadrados das medianas fixas | Atendido |
| Tabela de explosão combinatória (4.1.6) | CSV de amostras, resumo e projeções até 20, com natureza medida/estimada | Atendido |
| Economia da origem fixa | Modos fixo/livre na mesma matriz, razão de rotas n; relatório questão 1 | Atendido |
| Limiar de minutos | Uma coleta complementar concluiu n=12 em 76,40297299996018 s | Observado nesse ambiente, com uma repetição |
| P, NP e heurísticas (4.2) | Questão 4 do relatório, contraexemplo guloso e métodos complementares | Atendido, com ressalvas formais abaixo |
| Aumentar a faixa na web | Opções avançadas até 20 por padrão; comparação complementar até 10 | Ampliado nesta revisão |
| Interromper sem perder coletas completas | Cancelamento, limite opcional por chamada, checkpoints e exportação | Validado em diretórios temporários |

## Precisões teóricas

O modelo didático T(n)=n! conta as somas de arestas, não todas as operações
primitivas Python nem segundos. R=(n−1)! conta rotas. O relógio mede segundos
reais do solver; c converte o modelo em uma curva empírica, sem provar a ordem.
Sem fixar, R=n! e as somas são n·n!, portanto Θ(n·n!) nesta implementação.

O exemplo 2T(n−1)+c da seção 4.2.2 tem ordem Θ(2ⁿ); ele ilustra outra árvore
de recursão e não é a recorrência da enumeração do TSP aqui implementada.
Altura linear da recursão, isoladamente, não prova tempo exponencial: também
importam o número de ramificações e o trabalho em cada nó.

P e NP são classes de problemas de decisão, com P contida em NP. NP não
significa que todos os seus problemas sejam intratáveis. A formulação padrão
de decisão do TSP com custos inteiros é NP-completa; a otimização é NP-difícil.
O experimento usa instâncias euclidianas em ponto flutuante e não prova P≠NP,
questão ainda em aberto. Ordenação é um problema de função; Merge Sort fornece
a comparação de crescimento polinomial Θ(n log n) usada na discussão didática.

O guloso é polinomial, mas não garante o ótimo. O relatório apresenta um
contraexemplo reproduzível. 2-opt é busca local, não garantia de ótimo nem de
convergência em número polinomial de passadas. Os métodos complementares
não substituem nem aceleram a força bruta exigida.

## Interpretação do limite prático

O enunciado propõe n=3..10 ou o máximo suportado sem travar. Não exige falha
física, esgotamento de memória nem travamento do sistema. Tempos de minutos
ou horas já demonstram a dificuldade prática. A enumeração usa um processo
de cálculo e não materializa todas as permutações em memória.

O botão de preparação prolongada seleciona 10..14, uma repetição e limite 0;
apenas apresenta o plano. Para medir a dispersão, faça repetições quando o
custo permitir. A origem fixa deve continuar sendo a coleta principal.
O modo sem fixar serve à comparação e custa n vezes mais avaliações no mesmo n.

Durante uma repetição longa a contagem de chamadas fica estável. O tempo
decorrido do coordenador pode avançar, mas não mede rotas já avaliadas ou ETA.
Apenas uma chamada completa fornece ótimo, contagens observadas e tempo do
solver. Um limite voluntário interrompe toda a tarefa; não é evidência de falha
da máquina e não fornece um novo ponto da curva. O cancelamento não retoma uma
permutação parcial ao reiniciar. As amostras completas permanecem recuperáveis.

## Evidências desta revisão

A suíte anterior de 39 testes foi ampliada para 45, com seis verificações de
planos grandes, duração, interrupção e preservação de amostras. O teste n=13
usa o processo real e cancela a execução; não conclui o benchmark desse tamanho.
Detalhes e limitações estão em `VALIDACAO.md`. O relatório conserva os tempos
originais e separa coletas complementares. A revisão não inicia experimentos
de horas automaticamente e mantém a identificação acadêmica informada pelo grupo.

## Referências

- Universidade de Vila Velha. Projeto e Análise de Algoritmos. Unidade 4,
  seções 4.1 e 4.2. Material da disciplina fornecido para a atividade.
- Clay Mathematics Institute. [P vs NP](https://www.claymath.org/millennium/p-vs-np/).
  Consulta em 5 de novembro de 2026.
