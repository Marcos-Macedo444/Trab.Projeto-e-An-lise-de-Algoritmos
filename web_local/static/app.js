'use strict';
const $ = id => document.getElementById(id);
const ativos = new Set(['pendente','preparando','aquecendo','calculando','exportando','cancelando']);
const nomes = {bruta:'Força bruta (exata)',held_karp:'Held-Karp (exato)',guloso:'Guloso (heurístico)',dois_opt:'Guloso + 2-opt (heurístico)'};
const estados = {pendente:'Pendente',preparando:'Preparando',aquecendo:'Aquecendo',calculando:'Executando',exportando:'Exportando',concluido:'Concluído',cancelando:'Cancelando',cancelado:'Cancelado',falhou:'Falhou',interrompido:'Interrompido'};
let selecionada = '', ativa = null, dados = null, versao = '', tetos = {fixo:20,livre:20,comparacao:10};
let enviando = false, planejado = '', excluindo = false;
const dec = x => x == null ? '—' : Number(x).toLocaleString('pt-BR',{maximumFractionDigits:6});
const cont = x => x == null ? '—' : BigInt(String(x)).toLocaleString('pt-BR');
function erro(msg){ $('erro').textContent=msg || ''; $('erro').hidden=!msg; }
async function api(url, body){
  const r=await fetch(url,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const v=await r.json(); if(!r.ok) throw Error(v.erro || `HTTP ${r.status}`); return v;
}
function config(){
  const tipo=$('tipo').value, c={tipo,repeticoes:Number($('repeticoes').value),semente:Number($('semente').value),avancado:$('avancado').checked,limite_segundos:Number($('limite-segundos').value)};
  if(tipo==='benchmark') Object.assign(c,{nmin:Number($('nmin').value),nmax:Number($('nmax').value),sem_fixar:$('sem-fixar').checked,nmax_sem_fixar:Number($('nmax-sem-fixar').value)});
  else c.n=Number($('n').value);
  return c;
}
function atualizarLimites(){
  const tipo=$('tipo').value, adv=$('avancado').checked;
  const max=adv?tetos.fixo:Math.min(10,tetos.fixo);
  $('nmin').max=max; $('nmax').max=max;
  $('n').max=tipo==='comparacao'?Math.min(max,tetos.comparacao):max;
  $('nmax-sem-fixar').max=adv?tetos.livre:Math.min(8,tetos.livre);
  $('limites-ajuda').textContent=`Padrão: até ${Math.min(10,tetos.fixo)} fixo / ${Math.min(8,tetos.livre)} sem fixar. Prolongado: até ${tetos.fixo} fixo / ${tetos.livre} sem fixar. Comparação complementar: até ${tetos.comparacao}.`;
  $('preparar-longo').textContent=`Preparar faixa prolongada (${Math.min(10,tetos.fixo)} a ${Math.min(14,tetos.fixo)})`;
}
function adaptar(){
  const tipo=$('tipo').value, bench=tipo==='benchmark';
  $('faixa').hidden=!bench; $('livre').hidden=!bench; $('unica').hidden=bench;
  ['nmin','nmax','nmax-sem-fixar'].forEach(id=>$(id).disabled=!bench);
  $('n').disabled=bench;
  $('teto-livre').hidden=!bench||!$('sem-fixar').checked;
  $('nmax-sem-fixar').disabled=!bench||!$('sem-fixar').checked;
  atualizarLimites();
  $('tipo-ajuda').textContent=bench?'Enumera todas as rotas, sem poda, e avalia todas as arestas.':tipo==='demo'?'Resolve uma instância e desenha o ciclo completo.':'Compara quatro métodos na mesma matriz. Heurísticas não garantem o ótimo.';
  planejado=''; $('plano').textContent='Confira o plano antes de iniciar.';
}
function tabela(id,colunas,linhas){
  const host=$(id); host.replaceChildren();
  if(!linhas.length){const p=document.createElement('p');p.className='empty';p.textContent='Nenhum resultado ainda.';host.append(p);return;}
  const t=document.createElement('table'),head=t.createTHead().insertRow();
  colunas.forEach(([titulo])=>{const th=document.createElement('th');th.scope='col';th.textContent=titulo;head.append(th);});
  const body=t.createTBody();linhas.forEach(l=>{const row=body.insertRow();colunas.forEach(([,f])=>row.insertCell().textContent=f(l));});host.append(t);
}
async function plano(){
  if(!$('config').reportValidity()) return null;
  const c=config(), p=await api('/api/planejar',c);
  planejado=JSON.stringify(c);
  tabela('plano',[['n',g=>g.n],['Modo',g=>g.modo],['Método',g=>g.algoritmo],['Rotas/chamada',g=>cont(g.rotas_esperadas)],['Arestas/chamada',g=>cont(g.arestas_esperadas)]],p.grupos);
  const titulo=document.createElement('p');titulo.textContent=`${p.chamadas} chamadas planejadas. Contagens por execução.`;$('plano').prepend(titulo);
  if(p.aviso){const w=document.createElement('p');w.className='warning';w.textContent=p.aviso;$('plano').prepend(w);}
  (p.avisos||[]).forEach(aviso=>{const w=document.createElement('p');w.className='warning';w.textContent=aviso;$('plano').prepend(w);});
  const limite=document.createElement('p');limite.textContent=c.limite_segundos?`Limite: ${c.limite_segundos} s por repetição. Atingi-lo interrompe a tarefa.`:'Sem limite automático de duração. Use Cancelar tarefa para interromper.';$('plano').prepend(limite);
  return p;
}
$('planejar').addEventListener('click',()=>plano().catch(e=>erro(e.message)));
$('tipo').addEventListener('change',()=>{ $('n').value=$('tipo').value==='comparacao'?8:5;$('repeticoes').value=$('tipo').value==='benchmark'?3:1;adaptar(); });
$('avancado').addEventListener('change',adaptar);
$('sem-fixar').addEventListener('change',adaptar);
$('preparar-longo').addEventListener('click',()=>{
  $('tipo').value='benchmark';$('avancado').checked=true;
  $('nmin').value=Math.min(10,tetos.fixo);$('nmax').value=Math.min(14,tetos.fixo);
  $('repeticoes').value=1;$('sem-fixar').checked=false;$('limite-segundos').value=0;
  adaptar();plano().catch(e=>erro(e.message));
});
$('config').addEventListener('input',()=>{planejado='';});
$('config').addEventListener('submit',async ev=>{
  ev.preventDefault();if(enviando||ativa||excluindo)return; enviando=true;$('iniciar').disabled=true;erro('');
  try{
    if(planejado!==JSON.stringify(config())){await plano();const p=document.createElement('p');p.textContent='Plano conferido. Clique em Iniciar experimento novamente para confirmar.';$('plano').prepend(p);return;}
    const t=await api('/api/tarefas',config());selecionada=t.id;ativa=t.id;versao='';await atualizar();
  }catch(e){erro(e.message);}finally{enviando=false;$('iniciar').disabled=!!ativa||excluindo;}
});
$('cancelar').addEventListener('click',async()=>{
  if(!ativa)return;$('cancelar').disabled=true;
  try{await api(`/api/tarefas/${ativa}/cancelar`,{});versao='';}catch(e){erro(e.message);}
});
$('historico').addEventListener('change',async()=>{selecionada=$('historico').value;versao='';try{await atualizar();}catch(e){erro(e.message);}});
function limparResultados(){
  dados=null;versao='';
  $('estado').textContent='Nenhum resultado ainda';
  $('contagem').textContent='0 / 0 chamadas';$('barra').max=1;$('barra').value=0;
  $('atividade').textContent='Configure um experimento para iniciar uma nova coleta.';
  $('chamada-decorrida').textContent='';
  $('duracao').textContent='O progresso representa chamadas, não tempo restante.';
  ['razao','config-usada','coordenadas'].forEach(id=>$(id).textContent='');
  $('rota').textContent='Nenhuma rota concluída.';$('custo').textContent='—';
  $('mapa').replaceChildren();
  opcoes($('instancia'),[['','Nenhuma instância']],'');
  opcoes($('solucao'),[['','Aguardando resultado']],'');
  ['resumo','amostras','projecoes','matriz'].forEach(id=>tabela(id,[],[]));
  $('c-ajuste').textContent='Nenhum resultado ainda.';
  $('grafico-area').hidden=true;$('grafico').removeAttribute('src');
  $('downloads').replaceChildren();
}
$('excluir-todos').addEventListener('click',async()=>{
  if(excluindo||ativa)return;
  excluindo=true;$('excluir-todos').disabled=true;$('iniciar').disabled=true;erro('');
  try{
    const previa=await api('/api/experimentos/exclusao');
    if(!previa.quantidade){$('exclusao-resultado').textContent='Nenhum experimento de trabalho para excluir.';return;}
    const texto=`Excluir ${previa.quantidade} experimento(s) de trabalho: ${previa.web} web e ${previa.cli} de terminal?\n\nOs resultados e arquivos dessas execuções serão removidos. As evidências oficiais, o código e os testes serão preservados. Esta operação não pode ser desfeita.`;
    if(!window.confirm(texto))return;
    const resultado=await api('/api/experimentos/excluir-todos',{confirmacao:previa.confirmacao});
    if(atualizando)await atualizando.catch(()=>{});
    selecionada='';limparResultados();
    $('exclusao-resultado').textContent=`${resultado.removidos} execução(ões) removida(s).${resultado.falhas.length?' '+resultado.falhas.length+' execução(ões) não foram completamente removidas; verifique arquivos em uso e permissões.':''}`;
    await atualizar();
  }catch(e){erro(e.message);}finally{excluindo=false;await atualizar().catch(e=>erro(e.message));}
});
function opcoes(select,lista,valor){
  const iguais=select.options.length===lista.length&&lista.every(([v,t],i)=>select.options[i].value===v&&select.options[i].textContent===t);
  if(!iguais){select.replaceChildren();lista.forEach(([v,t])=>{const o=document.createElement('option');o.value=v;o.textContent=t;select.append(o);});}
  if(lista.some(([v])=>v===valor))select.value=valor;
}
function desenhar(){
  if(!dados)return;
  const n=$('instancia').value, inst=dados.instancias[n];
  const am=dados.amostras.filter(a=>String(a.n)===n);
  const anterior=$('solucao').value;
  opcoes($('solucao'),am.length?am.map((a,i)=>[String(i),`${nomes[a.algoritmo]||a.algoritmo} · ${a.modo} · rep. ${a.repeticao}`]):[['','Nenhum resultado ainda']],anterior);
  const a=am[Number($('solucao').value)] || null;
  const svg=$('mapa');svg.replaceChildren();
  const ns='http://www.w3.org/2000/svg';
  function el(tipo,attrs,text){const e=document.createElementNS(ns,tipo);Object.entries(attrs).forEach(([k,v])=>e.setAttribute(k,String(v)));if(text)e.textContent=text;svg.append(e);return e;}
  if(inst&&inst.coordenadas){
    const xs=inst.coordenadas.map(c=>c[0]),ys=inst.coordenadas.map(c=>c[1]);
    const minX=Math.min(...xs),minY=Math.min(...ys),escala=Math.min(500/(Math.max(...xs)-minX||1),245/(Math.max(...ys)-minY||1));
    const pontos=inst.coordenadas.map(([x,y])=>[50+(x-minX)*escala,290-(y-minY)*escala]);
    if(a){const rota=a.rota_indices.concat(a.rota_indices[0]);el('polyline',{class:'cycle',points:rota.map(i=>pontos[i].join(',')).join(' ')});}
    const origem=a?a.rota_indices[0]:0;
    pontos.forEach(([x,y],i)=>{el('circle',{cx:x,cy:y,r:i===origem?7:6,class:i===origem?'origin':''});el('text',{x:x+11,y:y-10},`v${i+1}`);});
  }else el('text',{x:300,y:170,'text-anchor':'middle'},'Sem coordenadas verificadas para esta matriz.');
  $('rota').textContent=a?a.rota_indices.concat(a.rota_indices[0]).map(i=>`v${i+1}`).join(' → '):'Nenhuma rota completa para esta instância.';
  $('custo').textContent=a?`Custo ${dec(a.custo)}`:'—';
  $('coordenadas').textContent=(inst?.origem_coordenadas||'')+' · Coordenadas euclidianas, não geográficas.';
  tabela('matriz',[['',r=>`v${r.i+1}`],...(inst?.matriz||[]).map((_,j)=>[`v${j+1}`,r=>dec(r.valores[j])])],(inst?.matriz||[]).map((valores,i)=>({i,valores})));
}
$('instancia').addEventListener('change',()=>{$('solucao').value='';desenhar();});
$('solucao').addEventListener('change',desenhar);
function mostrarResultados(d,s){
  dados=d;const nAnt=$('instancia').value;
  opcoes($('instancia'),Object.keys(d.instancias).map(n=>[n,`${n} cidades`]),nAnt);desenhar();
  $('c-ajuste').textContent=d.config.tipo==='comparacao'?'Comparação complementar: ajuste fatorial não aplicado. Exatos e heurísticos identificados.':d.c==null?'c indisponível: nenhuma amostra fixa concluída.':`c = ${d.c.toExponential(7)} s ${d.c_provisorio?'(provisório)':''}. Mínimos quadrados das medianas fixas. ${new Set(d.resumo.filter(r=>r.modo==='fixo').map(r=>r.n)).size===1?'Somente um n: não valida o crescimento empírico.':''}`;
  tabela('resumo', [['n',r=>r.n],['Modo / método',r=>r.algoritmo?nomes[r.algoritmo]:r.modo],['Repetições',r=>`${r.repeticoes_concluidas}/${r.repeticoes_previstas}${r.parcial?' (parcial)':''}`],['Mediana (s)',r=>dec(r.tempo_s)],['Mínimo (s)',r=>dec(r.minimo_s)],['Máximo (s)',r=>dec(r.maximo_s)],['Custo',r=>dec(r.custo??r.custo_otimo)],['Rotas observadas',r=>cont(r.rotas_observadas_por_execucao)],['Rotas esperadas',r=>cont(r.rotas_esperadas_por_execucao)],['Arestas observadas',r=>cont(r.arestas_observadas_por_execucao)],['Arestas esperadas',r=>cont(r.arestas_esperadas_por_execucao)],['Erro relativo (%)',r=>dec(r.erro_percentual)]], d.resumo);
  tabela('amostras',[['n',a=>a.n],['Modo',a=>a.modo],['Método',a=>nomes[a.algoritmo]],['Rep.',a=>a.repeticao],['Tempo (s)',a=>dec(a.tempo_s)],['Custo',a=>dec(a.custo)],['Rotas',a=>cont(a.rotas_observadas)],['Arestas',a=>cont(a.arestas_observadas)]],d.amostras);
  tabela('projecoes',[['n',p=>p.n],['Rotas fixas',p=>cont(p.rotas_fixas)],['Rotas livres',p=>cont(p.rotas_sem_fixar)],['Arestas fixas',p=>cont(p.arestas_fixas)],['Arestas livres',p=>cont(p.arestas_sem_fixar)],['Tempo estimado (s)',p=>dec(p.tempo_estimado_s)],['Natureza',p=>p.natureza]],d.projecoes);
  const grafico=s.arquivos.includes('grafico_tsp.png')&&!ativos.has(s.estado);
  $('grafico-area').hidden=!grafico;
  if(grafico)$('grafico').src=`/api/tarefas/${s.id}/arquivos/grafico_tsp.png`;
  $('downloads').replaceChildren();
  if(ativos.has(s.estado)||!s.arquivos.length){const p=document.createElement('p');p.className='hint';p.textContent='Arquivos disponíveis ao finalizar. Checkpoints completos já aceitos são preservados.';$('downloads').append(p);}
  else s.arquivos.forEach(nome=>{const a=document.createElement('a');a.href=`/api/tarefas/${s.id}/arquivos/${encodeURIComponent(nome)}`;a.textContent=nome;a.download=nome;$('downloads').append(a);});
}
let atualizando=null;
async function atualizar(){
  if(atualizando)return atualizando;
  atualizando=(async()=>{
    const lista=await api('/api/tarefas');ativa=lista.ativa;tetos=lista.tetos;atualizarLimites();
    $('iniciar').disabled=!!ativa||enviando||excluindo;
    $('excluir-todos').disabled=!!ativa||enviando||excluindo||!lista.tarefas.some(t=>!t.protegida);
    if(selecionada&&!lista.tarefas.some(t=>t.id===selecionada)){selecionada='';limparResultados();}
    if(!selecionada)selecionada=ativa||lista.tarefas.find(t=>t.origem==='web')?.id||'';
    $('cancelar').disabled=!ativa||selecionada!==ativa;
    opcoes($('historico'),[['','Selecione uma coleta'],...lista.tarefas.map(t=>[t.id,`${t.protegida?'OFICIAL':t.origem.toUpperCase()} · ${t.inicio?new Date(t.inicio).toLocaleString('pt-BR'):t.id} · ${estados[t.estado]||t.estado} · ${t.concluidas}/${t.planejadas}`])],selecionada);
    if(!selecionada)return;
    const s=await api(`/api/tarefas/${selecionada}`);
    $('estado').textContent=estados[s.estado]||s.estado;$('contagem').textContent=`${s.concluidas} / ${s.planejadas} chamadas`;
    $('barra').max=s.planejadas||1;$('barra').value=s.concluidas;
    $('atividade').textContent=s.atual?`n=${s.atual.n} · ${s.atual.modo} · ${nomes[s.atual.algoritmo]} · repetição ${s.atual.repeticao} — ${s.estado==='calculando'?'calculando esta repetição':estados[s.estado]}`:`${s.origem==='cli'?'Evidência registrada pela CLI. ':''}${estados[s.estado]||s.estado}.`;
    $('duracao').textContent=`${s.duracao_total_s==null?'Duração total não registrada':dec(s.duracao_total_s)+' s de duração total'} · Progresso por chamadas, não tempo restante.`;
    $('chamada-decorrida').textContent=s.duracao_chamada_s!=null?`Repetição em andamento há ${dec(s.duracao_chamada_s)} s (coordenador). Não é medição completa do solver. O contador avança apenas ao concluir uma chamada.`:s.interrupcao?.chamada?`Chamada interrompida: n=${s.interrupcao.chamada.n}, ${s.interrupcao.chamada.modo}, repetição ${s.interrupcao.chamada.repeticao}. ${s.interrupcao.duracao_observada_s==null?'':dec(s.interrupcao.duracao_observada_s)+' s observados pelo coordenador.'} Sem medição completa desta chamada.`:'';
    $('razao').textContent=s.razao||'';
    const cfg=s.config;
    $('config-usada').textContent=`Configuração desta coleta: ${cfg.tipo||'benchmark CLI'} · ${cfg.n!=null?'n='+cfg.n:'n='+cfg.nmin+'..'+cfg.nmax} · ${cfg.repeticoes} repetição(ões) · semente ${cfg.semente??42}${cfg.sem_fixar?' · também sem fixar até '+cfg.nmax_sem_fixar:''} · ${cfg.limite_segundos?'limite '+cfg.limite_segundos+' s por repetição':'sem limite automático'}.`;
    const v=`${s.id}:${s.sequencia}:${s.estado}`;
    if(v!==versao){const d=await api(`/api/tarefas/${s.id}/resultados`);mostrarResultados(d,s);versao=v;}
  })();
  try{await atualizando;}finally{atualizando=null;}
}
async function poll(){try{await atualizar();}catch(e){erro(e.message);}finally{setTimeout(poll,1000);}}
adaptar();poll();
