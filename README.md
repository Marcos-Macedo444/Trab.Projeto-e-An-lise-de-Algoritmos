# Problema do Caixeiro Viajante

Implementamos uma aplicação local para investigar o crescimento fatorial da
força bruta no TSP. Representamos cidades por coordenadas e matriz de custos,
medimos o solver Python e comparamos tempos reais com o modelo c·n!.
A interface permite configurar experimentos, visualizar rotas e consultar resultados.

## Requisitos e instalação

Python 3.10 ou superior. Validado no Windows com Python 3.14.3.
Na pasta do projeto, abra o PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-web.txt
.\.venv\Scripts\python.exe iniciar_web.py
```

Abra **http://127.0.0.1:5000**. Para outra porta, acrescente `--porta 5001`.
A execução direta dispensa ativar a venv. Flask e Waitress atendem apenas em
loopback; não são necessários Docker, banco, autenticação ou serviços externos.
Após instalar as dependências, a aplicação funciona sem acesso à internet.
Encerre com Ctrl+C e aguarde a exportação.

## Interface

- **Força bruta:** faixa de cidades, repetições e semente; comparação opcional
  sem fixar a origem.
- **Demonstração da rota:** uma instância com cidades, ciclo, custo e matriz.
- **Comparar algoritmos:** força bruta, Held-Karp, vizinho mais próximo e 2-opt
  na mesma matriz. Os dois últimos são heurísticos e não garantem o ótimo.

Confira o plano antes de iniciar. O primeiro clique com uma configuração nova
mostra o plano; o seguinte inicia o cálculo. Há uma tarefa por vez, em processo
separado. O progresso conta chamadas concluídas; durante uma chamada longa ele
pode permanecer estável. Recarregar a página mantém a visualização da tarefa.
Cancelar preserva as chamadas completas, sem retomar uma permutação parcial.

**Opções avançadas** reúne execução prolongada e limites. Padrão: até 10 cidades
fixando a origem ou 8 sem fixar; prolongado: até 20 em ambos os modos.
A comparação complementar tem teto 10. O botão prolongado prepara 10..14,
uma repetição e limite 0, sem iniciar cálculo. Os tetos são configuráveis:

```powershell
.\.venv\Scripts\python.exe iniciar_web.py --max-fixo 20 --max-livre 20 --max-comparacao 10
```

O limite por repetição aceita 0 (sem limite) ou até 604800 segundos. Atingi-lo
interrompe toda a tarefa; a chamada incompleta não entra na curva. O tempo
decorrido exibido pelo coordenador é separado da medição científica do solver.
Aumente n gradualmente. O teto 20 não implica tempo viável. Mantenha o computador
ligado e sem suspensão; a aplicação não altera o plano de energia.

## Resultados e histórico

As exportações incluem CSV UTF-8 separado por ponto e vírgula, JSON, metadados,
gráfico e ZIP individual. A mediana é acompanhada de mínimo, máximo e amostras.
Gráficos e projeções são identificados como estimativas, não novas medições.
A configuração e o ambiente são registrados por coleta. Checkpoints guardam
chamadas completas com checksum; um encerramento inesperado pode perder a
chamada em andamento. Ao reiniciar, tarefas interrompidas não retomam o solver.

As **evidências oficiais** estão em [evidencias](evidencias/README.md), fora da
exclusão coletiva e somente para consulta na aplicação. São cópias dos arquivos
originais, com valores e gráficos preservados. Novos experimentos vão para
`resultados_web/`; novos benchmarks CLI usam a saída escolhida no comando.
O histórico também reconhece coletas CLI em `resultados/` e `meus_resultados/`.
**Excluir histórico** remove apenas as execuções de trabalho registradas,
exige confirmação com quantidade e fica bloqueado durante cálculo/exportação.
As evidências oficiais, o código e os testes são preservados. A exclusão é
permanente e pode falhar parcialmente por arquivos em uso ou permissões.

## Terminal

```powershell
.\.venv\Scripts\python.exe tsp_forca_bruta.py --demo 5
.\.venv\Scripts\python.exe tsp_forca_bruta.py --nmin 3 --nmax 10 --repeticoes 3 --sem-fixar --nmax-sem-fixar 8 --saida resultados
.\.venv\Scripts\python.exe tsp_eficiente.py --validar --nbruta 8
.\.venv\Scripts\python.exe tsp_eficiente.py --nbruta 8 --nhk 12
```

A CLI mede somente o solver e salva as chamadas completas ao terminar ou receber
Ctrl+C. Checkpoints por chamada e limite de duração são recursos da web.
Para usar apenas a CLI, instale `requirements.txt`. A força bruta enumera todas
as rotas, sem poda: fixa (n−1)! rotas e n! somas; livre n! rotas e n·n! somas.
As duas orientações permanecem contadas. Não use `python -O` nas validações.

## Validação e materiais

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

- [Relatório](RELATORIO.md): metodologia, resultados, questões e referências.
- [Identificação acadêmica](DADOS_ACADEMICOS.md).
- [Resultados selecionados](RESULTADOS_SELECIONADOS.md).
- [Validação](docs/VALIDACAO.md).
- [Correspondência com a Unidade 4](docs/REVISAO_UNIDADE4.md).
- [Dependências e licenças](LICENCAS_DEPENDENCIAS.md).

As coletas são independentes: não misturamos amostras ou constantes de máquinas
ou protocolos distintos. Os requisitos locais da disciplina sobre declaração
de ferramentas e formatação da entrega devem ser observados pelo grupo.
