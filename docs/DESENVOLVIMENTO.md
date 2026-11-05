# Organização do código

- tsp_forca_bruta.py: cidades, matriz, permutações, solver, CSVs, gráfico e CLI.
- tsp_eficiente.py: Held-Karp, vizinho mais próximo, 2-opt e comparação CLI.
- tsp_experimentos.py: configuração, plano, validação e agregação da web.
- web_local/worker.py: processo spawn por grupo, com cronômetro ao redor do solver.
- web_local/tarefas.py: coordenação serial, checkpoints, cancelamento e exportação.
- web_local/historico.py: leitura de coletas de trabalho e evidências oficiais.
- web_local/exclusao.py: confirmação e validação dos diretórios removíveis.
- web_local/app.py: factory Flask e rotas locais.
- web_local/templates e static: interface, SVG, tabelas e polling.

As evidências oficiais têm prioridade sobre cópias de trabalho do mesmo id e são
somente para consulta. Novos experimentos usam resultados_web/. O índice oficial
pode omitir snapshots do histórico, sem regravar os arquivos da origem.
Não incluir callbacks no laço da força bruta ou somar custos incrementalmente:
o protocolo exige todas as n arestas em cada rota. Os CSVs preservam os contratos.

Para preparar os ZIPs: python tools/gerar_pacotes.py. O argumento opcional
--identificacao recebe o arquivo acadêmico completo, usado somente no ZIP do
professor. O manifesto é calculado sobre os bytes efetivamente distribuídos.
