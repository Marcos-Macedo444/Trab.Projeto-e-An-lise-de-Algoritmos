# Validação da entrega

Executamos os testes em Windows com Python 3.14.3 e as dependências declaradas.

```powershell
python -m unittest discover -s tests -v
```

Foram aprovados **47 testes em 15,097 s**. A saída está em `TESTES.txt`.
Os testes verificam ótimos, contagens, matrizes, sementes, métodos complementares,
CLI, exportação, processos, cronômetro, checkpoints, recuperação, cancelamento,
limites e restrições HTTP. A exclusão é exercitada em bases temporárias, inclusive
com junções do Windows, falhas parciais e confirmação desatualizada.

Os dois testes adicionais confirmam a preservação de evidências oficiais CLI/web
e a omissão de um snapshot histórico sem regravar seu arquivo. Nenhuma exclusão
foi executada na base de resultados do grupo. Os resultados acadêmicos anteriores
são copiados para evidencias/, sem refazer medições. Os testes controlados de
prazo não fornecem dados de benchmark para o relatório.

Uma instalação em computador limpo e outras versões de Python/Windows não
foram verificadas. O computador deve permanecer ligado e acordado durante
execuções longas. Interrupções não fornecem tempo completo ou solução ótima.

Conferimos a interface no navegador em desktop e em 390 px de largura, com
navegação por teclado e sem transbordamento horizontal da página. As tabelas
mantêm rolagem própria. Uma demonstração real n=4 concluiu seis rotas e 24 somas,
com ciclo fechado, custo e arquivos exportados. Um histórico oficial anterior
foi aberto sem regravar seus arquivos. A demonstração CLI n=5 confirmou 24 rotas
e 120 somas. As saídas descartáveis ficaram fora dos pacotes.

A árvore sintática executável da força bruta permaneceu igual à da cópia do
grupo; apenas a descrição inicial foi resumida. Os arquivos das sete evidências
selecionadas são idênticos em bytes aos originais. O manifesto usa os bytes
finais de cada distribuição, incluindo sua identificação acadêmica correspondente.

## Distribuições extraídas

| Pacote | Testes | Tempo da suíte | Inicialização |
|---|---|---|---|
| Compartilhamento do grupo | 47 aprovados | 16,006 s | Waitress, demonstração n=4, histórico e downloads |
| Entrega ao professor | 47 aprovados | 15,286 s | Waitress, demonstração n=4, histórico e downloads |

Cada pacote foi extraído em diretório novo com espaços no nome. Foram conferidos
o manifesto, os links locais, a identificação acadêmica do ZIP do professor e
a ausência de ambientes virtuais, caches, saídas descartáveis e ZIPs aninhados.
A reconstrução final acrescentou este registro e os atributos de preservação de
bytes do Git, sem alteração do código da aplicação ou dos testes validados.
