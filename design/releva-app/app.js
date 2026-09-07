const stage=document.querySelector(".stage"),
      screen=document.getElementById("screen"),
      tabbar=document.getElementById("tabbar"),
      toast=document.getElementById("toast"),
      fab=document.getElementById("fab"),
      fabEt=document.getElementById("fabEt");
function go(id){
  if(id==="cons-quien" && E.medicos.length===0){
    const act=document.querySelector(".scr.is-on");
    id = (act && act.dataset.scr==="cons-medico-nuevo") ? origenAlta : "cons-medico-nuevo";
  }
  if(id==="cons-medico-nuevo"){
    const bm=$("atrasMedico");
    if(bm) bm.dataset.go = E.medicos.length===0 ? (modoAlta==="adhoc" ? "grab-asignar" : "cons-cuando") : "cons-quien";
  }
  if(id==="cons-quien"){
    const rc=$("resumenCuando");
    if(rc){
      ver(rc, modoAlta!=="adhoc");
      $("cuandoDia").textContent="Lunes 28 de septiembre";
      $("cuandoDonde").textContent=horaElegida()+" · Hospital Italiano";
    }
    const aq=$("atrasQuien");
    if(aq) aq.dataset.go = modoAlta==="adhoc" ? "grab-asignar" : "cons-cuando";
  }
  if(id==="cons-cuando"){
    const cc=$("cerrarCuando");
    if(cc) cc.dataset.go = origenAlta;
    requestAnimationFrame(colocarRuedas);
  }
  if(id==="nota-nueva"){
    const act=document.querySelector(".scr.is-on");
    origenNota = (act && act.dataset.scr==="resumen") ? "resumen" : "consultas-prox";
    destinoNota = origenNota==="resumen" ? "r" : "n";
    document.querySelectorAll('[data-scr="nota-nueva"] [data-go]').forEach(x=>x.dataset.go=origenNota);
    const dst=$("notaPara");
    if(dst) dst.textContent = destinoNota==="r" ? "esta consulta"
      : (E.consulta ? E.consulta.quien+" · "+E.consulta.fecha : "la próxima consulta");
    requestAnimationFrame(()=>{const c=$("notaTexto"); if(c) c.focus();});
  }
  if(id==="bienvenida" || id==="onb1") cargarAlta();
  if(id==="onb2" || id==="onb3"){
    const escrito=(($("obNombre").textContent||"").trim())||nom();
    document.querySelectorAll('[data-scr="onb2"] .nom, [data-scr="onb3"] .nom').forEach(x=>x.textContent=escrito);
  }
  if(id==="elsa-editar"){
    const a=$("edNombre"), b2=$("edEdad");
    if(a) a.textContent=nomFull();
    if(b2) b2.textContent=E.persona.edad;
  }
  if(id==="consentimiento"){
    const cs=$("cerrarConsent"); if(cs) cs.dataset.go=origenGrab;
  }
  const t=document.querySelector('.scr[data-scr="'+id+'"]'); if(!t) return;
  document.querySelectorAll(".scr").forEach(s=>{
    s.classList.toggle("is-on",s===t);
    if(s!==t){s.classList.remove("colapsado"); const sc=s.querySelector(".scroll"); if(sc) sc.scrollTop=0;}
  });
  t.classList.remove("colapsado");
  const sc=t.querySelector(".scroll"); if(sc) sc.scrollTop=0;
  const cab=t.querySelector(".hdr");
  screen.dataset.sb = cab ? (cab.classList.contains("hdr-urg") ? "rojo"
                          : (cab.classList.contains("hdr-marca")||cab.classList.contains("hdr-raiz")) ? "naranja" : "claro")
                          : "claro";
  stage.dataset.dock=t.dataset.dock||"no";
  stage.classList.toggle("sin-bar", id==="consulta");
  stage.classList.remove("bajando");
  const f=t.dataset.fab;
  if(f && t.dataset.dock==="si"){
    const [et,destino,ico]=f.split("|");
    fabEt.textContent=et; fab.dataset.go=destino;
    fab.querySelector("use").setAttribute("href","#"+(ico||"ic-plus"));
    stage.dataset.fab="si";
  } else { stage.dataset.fab="no"; }
  if(!["hoy","estudios","consultas","consultas-prox","perfil"].includes(id)){ toast.classList.remove("ver"); }
  const tab=t.dataset.tab||"";
  tabbar.querySelectorAll(".tab").forEach(b=>b.setAttribute("aria-selected",String(b.dataset.tab===tab)));
}
document.querySelectorAll(".scroll").forEach(sc=>{
  let ultimo=0;
  sc.addEventListener("scroll",()=>{
    const y=sc.scrollTop, scr=sc.closest(".scr");
    if(scr) scr.classList.toggle("colapsado", y>10);
    if(y>56 && y>ultimo+4) stage.classList.add("bajando");
    else if(y<ultimo-4 || y<40) stage.classList.remove("bajando");
    ultimo=y;
  },{passive:true});
});
let relojToast=null;
const E={persona:{nombre:"Elsa", apellido:"Fernández", edad:"78", vinculo:"Mi mamá", cuadro:"", condiciones:[], alergias:[]},
  consulta:null, notasRes:[], pendientes:[], estudios:[], notas:[], anteriores:[], medicos:[], cuidadores:[]};
const $=id=>document.getElementById(id);
const ver=(el,on)=>{ if(el) el.style.display = on ? "" : "none"; };
const nom=()=>E.persona.nombre||"tu ser querido";
const nomFull=()=>(E.persona.nombre+" "+E.persona.apellido).trim()||nom();
function pintarNombre(){
  document.querySelectorAll(".nom").forEach(x=>x.textContent=nom());
  document.querySelectorAll(".nom-full").forEach(x=>x.textContent=nomFull());
  document.querySelectorAll(".edad").forEach(x=>x.textContent=E.persona.edad?E.persona.edad+" años":"");
}

function mostrarToast(txt){
  toast.querySelector(".txt").textContent=txt||"Listo";
  toast.classList.add("ver");
  clearTimeout(relojToast);
  relojToast=setTimeout(()=>toast.classList.remove("ver"),6000);
}

function fila(html,extra){
  const b=document.createElement("button");
  b.className="lista-item nuevo-item"+(extra?" "+extra:"");
  b.innerHTML=html; return b;
}
const chev='<span class="chev"><svg class="i"><use href="#ic-fwd"></use></svg></span>';
function filaNota(n,i,lista){
  return '<button class="nota-fila" data-nota-hecha="'+(lista||"n")+":"+i+'">'+
    '<span class="check'+(n.hecha?" on":"")+'"><svg class="i"><use href="#ic-check"></use></svg></span>'+
    '<span class="nota-tx'+(n.hecha?" hecha":"")+'">'+n.t+'</span></button>';
}

function render(){
  pintarNombre();
  const hayAlgo = E.consulta || E.pendientes.length || E.estudios.length;
  /* ---- Inicio ---- */
  ver($("bDiaUno"), !hayAlgo);
  ver($("bAccesos"), true);
  ver($("bPendientes"), hayAlgo);
  ver($("bConsulta"), !!E.consulta);
  ver($("bSinConsulta"), hayAlgo && !E.consulta);
  $("homeSub").textContent = hayAlgo ? "Martes 1 de septiembre" : "Hola, Mariana · martes 1 de septiembre";
  if(E.consulta){
    $("hcCuando").textContent="Tu próxima consulta";
    $("hcQuien").textContent=E.consulta.quien+" · "+E.consulta.esp;
    $("hcDonde").textContent=E.consulta.fecha+", "+E.consulta.cuando+" · "+E.consulta.donde;
    $("hcBoton").textContent = E.notas.length ? "Preparar la consulta · "+E.notas.length+(E.notas.length===1?" nota":" notas") : "Preparar la consulta";
  }
  const lp=$("listaPendientes"), agr=$("filaAgregarPend");
  [...lp.children].forEach(n=>{ if(n!==agr) n.remove(); });
  E.pendientes.forEach(x=>{
    const f=fila('<span class="check"><svg class="i"><use href="#ic-check"></use></svg></span>'+
      '<div class="stack-sm" style="gap:1px;flex:1"><span class="med-name">'+x.t+'</span><span class="small muted">'+x.d+'</span></div>');
    f.dataset.hecho=x.t;
    lp.insertBefore(f, agr);
  });
  const ult=E.estudios.slice(0,2);
  ver($("bUltimo"), ult.length>0);
  $("listaUltimo").innerHTML="";
  ult.forEach(x=>{
    const f=fila('<div class="thumb aten"><svg class="i"><use href="#ic-folder"></use></svg></div>'+
      '<div class="stack-sm" style="gap:1px;flex:1"><span class="med-name">'+x.t+'</span><span class="small muted">'+x.d+'</span></div>'+
      '<span class="pill pill-aten">Leyendo</span>');
    f.dataset.go="estudio"; f.dataset.origen="estudios|Estudios"; f.dataset.est=x.t+"|"+x.d;
    $("listaUltimo").appendChild(f);
  });

  /* ---- Consultas ---- */
  const hayCons = !!E.consulta || E.anteriores.length>0;
  ver($("consVacio"), !hayCons);
  ver($("consBuscar"), hayCons);
  ver($("consProxWrap"), !!E.consulta);
  ver($("consAntWrap"), E.anteriores.length>0);
  $("consSub").textContent = hayCons
    ? (E.consulta?"1 agendada":"") + (E.consulta&&E.anteriores.length?" · ":"") + (E.anteriores.length?E.anteriores.length+" anterior"+(E.anteriores.length>1?"es":""):"")
    : "Todavía no hay ninguna";
  $("listaProximas").innerHTML="";
  if(E.consulta){
    const f=fila('<div class="thumb" style="background:var(--marca-suave)"><svg class="i"><use href="#ic-today"></use></svg></div>'+
      '<div class="stack-sm" style="gap:2px;flex:1"><span class="med-name">'+E.consulta.quien+' · '+E.consulta.esp+'</span>'+
      '<span class="small" style="color:var(--marca-texto);font-weight:600">'+E.consulta.fecha+', '+E.consulta.cuando+'</span>'+
      '<span class="small muted">'+(E.notas.length?E.notas.length+" nota"+(E.notas.length>1?"s":"")+" lista"+(E.notas.length>1?"s":""):"Sin notas todavía")+'</span></div>'+chev);
    f.dataset.go="consultas-prox";
    $("listaProximas").appendChild(f);
  }

  /* ---- Estudios ---- */
  ver($("estVacio"), E.estudios.length===0);
  ver($("estWrap"), E.estudios.length>0);
  ver($("estFiltros"), E.estudios.length>0);
  const es=$("estSub");
  es.textContent = E.estudios.length ? E.estudios.length+" cargado"+(E.estudios.length>1?"s":"") : "";
  ver(es, E.estudios.length>0);
  $("listaEstudios").innerHTML="";
  E.estudios.forEach(x=>{
    const f=fila('<div class="thumb aten"><svg class="i"><use href="#ic-folder"></use></svg></div>'+
      '<div class="stack-sm" style="gap:1px;flex:1"><span class="med-name">'+x.t+'</span><span class="small muted">'+x.d+'</span></div>'+
      '<span class="pill pill-aten">Leyendo</span>');
    f.dataset.go="estudio"; f.dataset.origen="estudios|Estudios"; f.dataset.est=x.t+"|"+x.d;
    const del=document.createElement("span");
    del.className="borrar"; del.dataset.borrarEstudio=x.t;
    del.innerHTML='<svg class="i"><use href="#ic-x"></use></svg>';
    f.appendChild(del);
    $("listaEstudios").appendChild(f);
  });

  /* ---- Preparar ---- */
  if(E.consulta){
    $("proxQuien").textContent=E.consulta.quien+" · "+E.consulta.esp;
    $("proxSub").textContent=E.consulta.fecha+", "+E.consulta.cuando;
  }
  ver($("notasVacio"), E.notas.length===0);
  $("listaNotas").innerHTML="";
  E.notas.forEach((n,i)=>{
    const d=document.createElement("div"); d.className="card nuevo-item";
    d.innerHTML=filaNota(n,i);
    $("listaNotas").appendChild(d);
  });
  const lnc=$("notasEnConsulta");
  if(lnc){
    lnc.innerHTML="";
    E.notas.forEach((n,i)=>{
      const d=document.createElement("div"); d.className="med-row"; d.style.padding="10px 0";
      d.innerHTML=filaNota(n,i);
      lnc.appendChild(d);
    });
    ver($("consNotasCard"), E.notas.length>0);
  }

  /* ---- cuidadores invitados ---- */
  const lc=$("listaCuidadores");
  if(lc){
    lc.querySelectorAll(".invitado").forEach(n=>n.remove());
    const anclaInv=$("filaInvitar");
    E.cuidadores.forEach(c=>{
      const f=fila('<span class="av" style="width:44px;height:44px;font-size:16px;background:var(--suave);color:var(--gris)">'+c.n.charAt(0).toUpperCase()+'</span>'+
        '<div class="stack-sm" style="gap:1px;flex:1"><span class="med-name">'+c.n+'</span><span class="small muted">Invitación enviada</span></div>'+
        '<span class="pill pill-aten">Pendiente</span>',"invitado");
      lc.insertBefore(f, anclaInv);
    });
  }

  /* ---- asignar grabación ---- */
  const aa=$("asignarAgendada");
  if(aa){
    ver(aa, !!E.consulta);
    if(E.consulta){
      $("asignarQuien").textContent=E.consulta.quien+" · "+E.consulta.esp;
      $("asignarCuando").textContent="La que tenías agendada · "+E.consulta.fecha;
    }
  }
  ver($("resSinAsignar"), grabPara==="despues");
  const lnr=$("listaNotasRes");
  if(lnr){
    lnr.innerHTML="";
    E.notasRes.forEach((n,i)=>{
      const d=document.createElement("div"); d.className="med-row"; d.style.padding="10px 0";
      d.innerHTML=filaNota(n,i,"r");
      lnr.appendChild(d);
    });
  }
  const la=$("listaAsignar");
  if(la){
    la.innerHTML="";
    const opciones=[];
    if(E.consulta) opciones.push({n:E.consulta.quien+" · "+E.consulta.esp, d:"La que tenías agendada · "+E.consulta.fecha});
    E.anteriores.forEach(a=>opciones.push({n:a.q, d:"Consulta anterior"}));
    opciones.forEach(o=>{
      const b=document.createElement("button");
      b.className="opcion"; b.dataset.go="resumen"; b.dataset.asignarA=o.n;
      b.innerHTML='<div class="thumb" style="background:var(--marca-suave)"><svg class="i"><use href="#ic-today"></use></svg></div>'+
        '<span><b>'+o.n+'</b><span>'+o.d+'</span></span>'+chev;
      la.appendChild(b);
    });
    ver($("asignarExistentes"), opciones.length>0);
    $("lblNombreGrab").textContent = opciones.length ? "O ponele un nombre" : "Ponele un nombre";
  }

  /* ---- elegir médico ---- */
  const le=$("listaElegirMedico");
  if(le){
    le.innerHTML="";
    E.medicos.forEach(m=>{
      const b=document.createElement("button");
      b.className="opcion"; b.dataset.go="consultas"; b.dataset.medico=m.n; b.dataset.agendar="1";
      b.innerHTML='<div class="thumb"><svg class="i"><use href="#ic-user"></use></svg></div>'+
        '<span><b>'+m.n+'</b><span>'+m.e+'</span></span>'+chev;
      le.appendChild(b);
    });
    ver(le, E.medicos.length>0);
    ver(le.previousElementSibling, E.medicos.length>0);
  }

  /* ---- Elsa ---- */
  const ps=$("perfilSub");
  if(ps){
    const P=E.persona;
    ps.textContent=[P.edad?P.edad+" años":"", P.vinculo?P.vinculo.toLowerCase():"", "0+", "OSDE 210"].filter(Boolean).join(" · ");
  }
  const rc=$("resumenCuadro");
  if(rc){
    const P=E.persona;
    ver(rc, !!(P.cuadro||P.condiciones.length||P.alergias.length));
    ver($("cuadroTexto"), !!P.cuadro);
    $("cuadroTexto").textContent=P.cuadro;
    ver($("bloqueCondiciones"), P.condiciones.length>0);
    $("listaCondiciones").innerHTML=P.condiciones.map(c=>'<span class="pill pill-aten">'+c+'</span>').join("");
    ver($("bloqueAlergias"), P.alergias.length>0);
    $("listaAlergias").innerHTML=P.alergias.map(a=>'<span class="pill pill-urg">'+a+'</span>').join("");
  }
  const lm=$("listaMedicos");
  if(lm){
    lm.innerHTML="";
    E.medicos.forEach(m=>{
      const f=fila('<div class="thumb"><svg class="i"><use href="#ic-user"></use></svg></div>'+
        '<div class="stack-sm" style="gap:1px;flex:1"><span class="med-name">'+m.n+'</span><span class="small muted">'+m.e+'</span></div>'+
        '<span class="borrar" data-borrar-medico="'+m.n+'"><svg class="i"><use href="#ic-x"></use></svg></span>');
      lm.appendChild(f);
    });
    ver(lm, E.medicos.length>0);
    ver($("medVacio"), E.medicos.length===0);
  }
}

/* --- altas --- */
let ultimo=null;
function deshacer(){
  if(!ultimo) return;
  ultimo(); ultimo=null;
  toast.classList.remove("ver"); clearTimeout(relojToast);
  render();
}
document.getElementById("deshacer").addEventListener("click",deshacer);

function marcarChips(sel,valores){
  document.querySelectorAll(sel).forEach(c=>{
    const on=valores.indexOf(c.textContent.trim())>=0;
    c.classList.toggle("on",on);
    const tic=c.querySelector("svg");
    if(on && !tic) c.insertAdjacentHTML("afterbegin",'<svg class="i"><use href="#ic-check"></use></svg>');
    if(!on && tic) tic.remove();
  });
}
function cargarAlta(){
  const P=E.persona, v=(id,val)=>{const e=$(id); if(e) e.textContent=val;};
  v("obNombre",P.nombre); v("obApellido",P.apellido); v("obEdad",P.edad); v("obCuadro",P.cuadro);
  marcarChips("#obVinculo .chip",[P.vinculo]);
  marcarChips("#obCondiciones .chip",P.condiciones);
  marcarChips("#obAlergias .chip",P.alergias);
  marcarChips("#obSinAlergia .chip",P.alergias);
}
function guardarAlta(){
  const t=id=>((document.getElementById(id)||{}).textContent||"").trim();
  E.persona.nombre = t("obNombre") || "Elsa";
  E.persona.apellido = t("obApellido");
  E.persona.edad = t("obEdad").replace(/\D+/g,"");
  E.persona.cuadro = t("obCuadro");
  const marcados=sel=>[...document.querySelectorAll(sel)].filter(x=>x.classList.contains("on")).map(x=>x.textContent.trim());
  E.persona.condiciones = marcados("#obCondiciones .chip");
  E.persona.alergias = marcados("#obAlergias .chip");
  const nada=document.querySelector("#obSinAlergia .chip.on");
  if(nada) E.persona.alergias=[nada.textContent.trim()];
  const vin=document.querySelector("#obVinculo .chip.on");
  if(vin) E.persona.vinculo=vin.textContent.trim();
}
function guardarPersona(){
  const partes=(($("edNombre").textContent||"").trim()||"Elsa").split(/\s+/);
  E.persona.nombre=partes.shift();
  E.persona.apellido=partes.join(" ");
  E.persona.edad=(($("edEdad").textContent||"").trim()).replace(/\D+/g,"");
  render();
}
function reiniciar(){
  E.consulta=null; E.pendientes.length=0; E.estudios.length=0;
  E.notas.length=0; E.notasRes.length=0; E.anteriores.length=0; E.medicos.length=0; E.cuidadores.length=0;
  medicoElegido=null; modoAlta="agendar"; grabPara=null; ultimo=null;
  grabando=false; stage.classList.remove("grabando"); clearInterval(relojGrab); relojGrab=null;
  const ant=$("listaAnteriores"); if(ant) ant.innerHTML="";
  toast.classList.remove("ver");
  render();
}
function agregarPendiente(){
  const x={t:"Autorizar la ecografía de control", d:"Esta semana · de la consulta del 26/8", icono:"lock"};
  E.pendientes.unshift(x);
  ultimo=()=>{E.pendientes.splice(E.pendientes.indexOf(x),1);};
  render(); mostrarToast("Listo, lo agregué");
}
function agregarEstudio(origen){
  const x={t:"Estudio sin nombre", d:"1 de septiembre · desde "+origen};
  E.estudios.unshift(x);
  ultimo=()=>{E.estudios.splice(E.estudios.indexOf(x),1);};
  render(); mostrarToast("Lo estoy leyendo, te aviso");
}
function agregarNota(){
  const campo=$("notaTexto");
  const txt=(campo.textContent||"").trim();
  if(!txt) return;
  const x={t:txt, hecha:false};
  (destinoNota==="r" ? E.notasRes : E.notas).push(x);
  campo.textContent="";
  ultimo=null;
  render();
}
/* rueda de hora */
function armarRueda(el,desde,hasta,paso,inicial){
  el.innerHTML='<span class="pad"></span>'+
    Array.from({length:Math.floor((hasta-desde)/paso)+1},(_,k)=>{
      const v=desde+k*paso;
      return '<i data-v="'+v+'">'+String(v).padStart(2,"0")+'</i>';
    }).join("")+'<span class="pad"></span>';
  const marcar=()=>{
    const items=[...el.querySelectorAll("i")];
    const centro=el.scrollTop+el.clientHeight/2;
    let mejor=items[0], dist=Infinity;
    items.forEach(n=>{
      const d=Math.abs(n.offsetTop+n.offsetHeight/2-centro);
      if(d<dist){dist=d; mejor=n;}
    });
    items.forEach(n=>n.classList.toggle("sel",n===mejor));
    el.dataset.valor=mejor?.dataset.v??desde;
  };
  el.addEventListener("scroll",()=>{clearTimeout(el._t); el._t=setTimeout(marcar,110);},{passive:true});
  el.addEventListener("scrollend",marcar);
  el._colocar=()=>{
    if(!el._listo){ el.scrollTop=((inicial-desde)/paso)*40; el._listo=true; }
    marcar();
  };
}
const ruedaH=$("ruedaH"), ruedaM=$("ruedaM");
armarRueda(ruedaH,6,20,1,11); armarRueda(ruedaM,0,55,5,30);
function colocarRuedas(){ ruedaH._colocar(); ruedaM._colocar(); }
const horaElegida=()=>String(ruedaH.dataset.valor??11)+":"+String(ruedaM.dataset.valor??30).padStart(2,"0");

let medicoElegido=null, modoAlta="agendar", grabPara=null, origenAlta="consultas", origenGrab="hoy", origenNota="consultas-prox", destinoNota="n";
function guardarMedico(){
  const nom=($("medNombre").textContent||"").trim();
  const ape=($("medApellido").textContent||"").trim();
  const esp=($("medEsp").textContent||"").trim()||"Sin especialidad";
  medicoElegido={n:(nom+" "+ape).trim()||"Médico nuevo", e:esp, nuevo:true};
}
function crearAdHoc(){
  const m=medicoElegido||{n:"Médico",e:""};
  E.consulta={quien:m.n, esp:m.e, fecha:"Hoy, 1 de septiembre", cuando:"ahora", donde:"", adhoc:true};
  if(m.nuevo && !E.medicos.some(x=>x.n===m.n)) E.medicos.push({n:m.n,e:m.e});
  grabPara="agendada"; modoAlta="agendar";
  render();
}
function agendarConsulta(){
  const m=medicoElegido||{n:"Médico",e:""};
  const previa=E.consulta, eraNuevo=m.nuevo && !E.medicos.some(x=>x.n===m.n);
  E.consulta={quien:m.n, esp:m.e, fecha:"Lunes 28 de septiembre", cuando:horaElegida(), donde:"Hospital Italiano"};
  if(eraNuevo) E.medicos.push({n:m.n,e:m.e});
  ultimo=()=>{ E.consulta=previa; if(eraNuevo) E.medicos.pop(); };
  render();
  mostrarToast(eraNuevo ? "Turno agendado. Y lo guardé en los médicos de Elsa." : "Listo, agendé el turno");
}

/* grabación en segundo plano */
let grabando=false, seg=0, relojGrab=null;
const fmt=v=>Math.floor(v/60)+":"+String(v%60).padStart(2,"0");
function pintarTimer(){
  const a=$("timerGrande");
  if(a) a.textContent=fmt(seg);
}
function empezarGrabacion(){
  grabando=true; seg=0; stage.classList.add("grabando");
  clearInterval(relojGrab);
  relojGrab=setInterval(()=>{seg++; pintarTimer();},1000);
  pintarTimer();
}
function abrirEstudio(nombre,sub){
  $("estQuien").textContent=nombre;
  $("estSubDet").textContent=sub;
}
function abrirResumen(quien,esp,fecha){
  $("resQuien").textContent = esp ? quien+" · "+esp : quien;
  $("resSub").textContent=fecha;
}
function anotarAnterior(titulo,sub){
  E.anteriores.unshift({q:titulo});
  const ant=$("listaAnteriores");
  if(ant){
    const f=fila('<div class="thumb"><svg class="i"><use href="#ic-mic"></use></svg></div>'+
      '<div class="stack-sm" style="gap:1px;flex:1"><span class="med-name">'+titulo+'</span>'+
      '<span class="small muted">'+sub+'</span></div>'+chev);
    f.dataset.go="resumen"; f.dataset.res=titulo+"||hoy";
    ant.insertBefore(f, ant.firstChild);
  }
}
function terminarGrabacion(){
  if(!grabando){ render(); return; }
  grabando=false; stage.classList.remove("grabando");
  clearInterval(relojGrab); relojGrab=null;
  E.notasRes=E.notas.slice(); E.notas.length=0;
  if(grabPara==="despues"){
    abrirResumen("Consulta sin nombre","","Hoy · sin asignar");
  } else if(E.consulta){
    abrirResumen(E.consulta.quien, E.consulta.esp, "Hoy");
    anotarAnterior(E.consulta.quien+" · "+E.consulta.esp, "Hoy · 3 indicaciones");
    E.consulta=null;
    grabPara=null;
  }
  render();
}
function asignarGrabacion(titulo,sub){
  abrirResumen(titulo,"",sub);
  anotarAnterior(titulo, "Hoy · 3 indicaciones");
  if(E.consulta && titulo.indexOf(E.consulta.quien)===0){ E.consulta=null; E.notas.length=0; }
  grabPara=null;
  render(); mostrarToast("Guardada en "+titulo);
}

function origenEstudio(valor){
  const b=$("atrasEstudio"); if(!b) return;
  const [destino,etiqueta]=(valor||"estudios|Estudios").split("|");
  b.dataset.go=destino;
  const oj=$("estOjal"); if(oj) oj.textContent=etiqueta;
  const scr=document.querySelector('.scr[data-scr="estudio"]');
  if(scr) scr.dataset.tab = destino==="estudios" ? "estudios" : (destino==="consulta" ? "" : "consultas");
}

document.addEventListener("click",e=>{
  const bm=e.target.closest("[data-borrar-medico]");
  if(bm){
    const n=bm.dataset.borrarMedico, i=E.medicos.findIndex(x=>x.n===n);
    if(i>=0){ const m=E.medicos.splice(i,1)[0]; ultimo=()=>E.medicos.splice(i,0,m); render(); mostrarToast("Saqué a "+n); }
    return;
  }
  const be=e.target.closest("[data-borrar-estudio]");
  if(be){
    const t=be.dataset.borrarEstudio, i=E.estudios.findIndex(x=>x.t===t);
    if(i>=0){ const x=E.estudios.splice(i,1)[0]; ultimo=()=>E.estudios.splice(i,0,x); render(); mostrarToast("Estudio borrado"); }
    return;
  }
  const rl=e.target.closest("[data-rol]");
  if(rl){
    rl.parentElement.querySelectorAll("[data-rol]").forEach(x=>{
      const on=x===rl; x.classList.toggle("on",on);
      const tic=x.querySelector("svg");
      if(on && !tic) x.insertAdjacentHTML("afterbegin",'<svg class="i"><use href="#ic-check"></use></svg>');
      if(!on && tic) tic.remove();
    });
    return;
  }
  const hc=e.target.closest("[data-hecho]");
  if(hc){
    const x=E.pendientes.find(y=>y.t===hc.dataset.hecho);
    if(x){
      const pos=E.pendientes.indexOf(x);
      E.pendientes.splice(pos,1);
      ultimo=()=>{E.pendientes.splice(pos,0,x);};
      render(); mostrarToast("Hecho");
    }
    return;
  }
  const vi=e.target.closest("[data-vinculo]");
  if(vi){ marcarChips("#obVinculo .chip",[vi.textContent.trim()]); return; }
  const al=e.target.closest("[data-alergia]");
  if(al){
    al.classList.toggle("on");
    marcarChips("#obAlergias .chip",[...document.querySelectorAll("#obAlergias .chip.on")].map(x=>x.textContent.trim()));
    marcarChips("#obSinAlergia .chip",[]);
    return;
  }
  const an=e.target.closest("[data-alergia-no]");
  if(an){
    const ya=an.classList.contains("on");
    marcarChips("#obSinAlergia .chip", ya?[]:[an.textContent.trim()]);
    if(!ya) marcarChips("#obAlergias .chip",[]);
    return;
  }
  const cd=e.target.closest("[data-cond]");
  if(cd){
    cd.classList.toggle("on");
    marcarChips("#obCondiciones .chip",[...document.querySelectorAll("#obCondiciones .chip.on")].map(x=>x.textContent.trim()));
    return;
  }
  const nh=e.target.closest("[data-nota-hecha]");
  if(nh){
    const [lista,idx]=nh.dataset.notaHecha.split(":");
    const n=(lista==="r"?E.notasRes:E.notas)[+idx];
    if(n){ n.hecha=!n.hecha; render(); }
    return;
  }
  const b=e.target.closest("[data-go]");
  if(b){
    if(b.dataset.alta) guardarAlta();
    if(b.dataset.editarPersona) guardarPersona();
    if(b.dataset.res){ const [q,e2,f2]=b.dataset.res.split("|"); abrirResumen(q,e2,f2); }
    if(b.dataset.est){ const [n2,s2]=b.dataset.est.split("|"); abrirEstudio(n2,s2); }
    if(b.dataset.origen) origenEstudio(b.dataset.origen);
    if(b.dataset.go==="consulta" && !grabando) empezarGrabacion();
    if(b.dataset.terminar) terminarGrabacion();
    if(b.dataset.go==="cons-cuando" || b.dataset.go==="cons-quien"){
      const act=document.querySelector(".scr.is-on");
      if(act && act.dataset.dock==="si") origenAlta=act.dataset.scr;
    }
    if(b.dataset.reset) reiniciar();
    if(b.dataset.invitar){
      const n=($("invNombre").textContent||"Alguien").trim();
      const c={n:n};
      E.cuidadores.push(c);
      ultimo=()=>{E.cuidadores.splice(E.cuidadores.indexOf(c),1);};
      render(); mostrarToast("Invitación enviada a "+n);
    } else if(b.dataset.aviso){ mostrarToast(b.dataset.aviso); }
    if((b.dataset.go==="cons-cuando"||b.dataset.go==="cons-quien") && !b.dataset.asignar){
      modoAlta="agendar"; grabPara=null;
      const bt=$("btnMedicoNuevo"); if(bt) bt.textContent="Agregar el turno";
    }
    if(b.dataset.asignar){
      const act=document.querySelector(".scr.is-on");
      if(act && act.dataset.dock==="si") origenGrab=act.dataset.scr;
      grabPara=b.dataset.asignar;
      modoAlta = b.dataset.asignar==="adhoc" ? "adhoc" : "agendar";
      $("btnMedicoNuevo").textContent = modoAlta==="adhoc" ? "Agregar y empezar" : "Agregar el turno";
    }
    if(b.dataset.medico==="nuevo") guardarMedico();
    else if(b.dataset.medico){
      const m=E.medicos.find(x=>x.n===b.dataset.medico);
      if(m) medicoElegido={n:m.n,e:m.e};
    }
    if(modoAlta==="adhoc" && b.dataset.medico){ crearAdHoc(); go("consentimiento"); return; }
    go(b.dataset.go);
    if(b.dataset.asignarA) asignarGrabacion(b.dataset.asignarA,"Hoy");
    if(b.dataset.nombrar){
      const c=$("nombreGrab"), t=(c.textContent||"").trim()||"Consulta sin nombre";
      c.textContent=""; asignarGrabacion(t,"Hoy");
    }
    if(b.dataset.agregar) agregarPendiente();
    if(b.dataset.agendar) agendarConsulta();
    if(b.dataset.notaNueva) agregarNota();
    if(b.dataset.nuevoEstudio) agregarEstudio(b.dataset.nuevoEstudio);
    return;
  }
  const seg=e.target.closest(".segmentado button");
  if(seg){ seg.parentElement.querySelectorAll("button").forEach(x=>x.setAttribute("aria-selected",String(x===seg))); return; }
  const f=e.target.closest(".filtro");
  if(f){ f.parentElement.querySelectorAll(".filtro").forEach(x=>x.setAttribute("aria-pressed",String(x===f))); }
  const ch=e.target.closest(".chip, .check");
  if(ch && ch.classList.contains("check")) ch.classList.toggle("on");
});
render();
go("hoy");
