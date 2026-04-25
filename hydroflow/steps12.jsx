// Step 1 (Зона + создание теплицы) и Step 2 (Рецепт-визард с фазами).
// Заменяют Step1Zone и Step2Recipe из steps.jsx.
// Recipe определяет systemType / targetPh / targetEc — Шаг 3 их только показывает.

const { useState: useS12, useMemo: useM12 } = React;

// =================================================================
// STEP 1 — Зона  (теплица: выбрать ИЛИ создать inline; зона — как было)
// =================================================================
function Step1ZoneV2({ gh, zn, setGh, setZn, hints, greenhouses, onCreateGh }){
  const [createMode, setCreateMode] = useS12(false);
  const [draft, setDraft] = useS12({
    name:'', timezone:'Europe/Moscow', greenhouse_type_id:'film',
    description:'',
  });
  const uid = draft.name.trim()
    ? 'gh-' + draft.name.trim().toLowerCase().replace(/[^a-z0-9а-я]+/gi,'-').replace(/(^-|-$)/g,'')
    : 'gh-...';

  const submit = () => {
    if (!draft.name.trim()) return;
    onCreateGh({ ...draft, uid });
    setCreateMode(false);
    setDraft({ name:'', timezone:'Europe/Moscow', greenhouse_type_id:'film', description:'' });
  };

  const ghMeta = greenhouses.find(g=>g.id===gh.greenhouseId);

  return (
    <div style={{display:'grid',gridTemplateColumns:'1fr 320px',gap:16}}>
      <div style={{display:'flex',flexDirection:'column',gap:12}}>
        <Card title="Теплица"
          right={
            <div style={{display:'flex',gap:6}}>
              <Btn size="sm" variant={!createMode?'primary':'secondary'} onClick={()=>setCreateMode(false)}>Выбрать</Btn>
              <Btn size="sm" variant={createMode?'primary':'secondary'} onClick={()=>setCreateMode(true)} icon={<Ic.plus/>}>Создать</Btn>
              {!createMode && <Chip tone={gh.greenhouseId?'growth':'warn'} icon={gh.greenhouseId?<Ic.check/>:<Ic.warn/>}>
                {gh.greenhouseId? gh.greenhouseId.toUpperCase():'не выбрана'}
              </Chip>}
            </div>
          }>
          {!createMode ? (
            <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:12}}>
              <Field label="Теплица" required>
                <Select value={gh.greenhouseId} onChange={v=>setGh({...gh,greenhouseId:v})}
                  options={greenhouses.map(g=>({value:g.id,label:`${g.id.toUpperCase()} · ${g.name} · ${g.area} м²`}))}
                  placeholder="— выберите —"/>
              </Field>
              <Field label="Тип конструкции">
                <Input value={ghMeta?.type || '—'} mono readOnly/>
              </Field>
              {ghMeta && (
                <div style={{gridColumn:'span 2',display:'grid',gridTemplateColumns:'100px 1fr',gap:14}}>
                  <StripePlaceholder w={100} h={82} label="GH plan"/>
                  <div style={{display:'grid',gridTemplateColumns:'repeat(4,1fr)',gap:10,alignContent:'center'}}>
                    <Stat label="Тип" value={ghMeta.type}/>
                    <Stat label="Площадь" value={`${ghMeta.area} м²`} mono/>
                    <Stat label="Зоны" value={ghMeta.zones} mono/>
                    <Stat label="Узлы online" value={`${ghMeta.nodes}/${ghMeta.nodes}`} mono tone="growth"/>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:12}}>
              <Field label="Название" required hint={`UID будет сгенерирован: ${uid}`}>
                <Input value={draft.name} onChange={v=>setDraft({...draft,name:v})} placeholder="Main Greenhouse"/>
              </Field>
              <Field label="Часовой пояс">
                <Input value={draft.timezone} onChange={v=>setDraft({...draft,timezone:v})} mono placeholder="Europe/Moscow"/>
              </Field>
              <Field label="Тип теплицы">
                <Select value={draft.greenhouse_type_id} onChange={v=>setDraft({...draft,greenhouse_type_id:v})}
                  options={[
                    {value:'film',label:'Плёночная'},
                    {value:'glass',label:'Стеклянная'},
                    {value:'poly',label:'Поликарбонат'},
                    {value:'container',label:'Контейнер'},
                  ]}/>
              </Field>
              <Field label="Площадь" hint="м² (опц.)">
                <Input value={draft.area||''} onChange={v=>setDraft({...draft,area:v})} mono suffix="м²"/>
              </Field>
              <div style={{gridColumn:'span 2'}}>
                <Field label="Описание">
                  <Input value={draft.description} onChange={v=>setDraft({...draft,description:v})} placeholder="Описание теплицы…"/>
                </Field>
              </div>
              <div style={{gridColumn:'span 2',display:'flex',justifyContent:'flex-end',gap:8,marginTop:4}}>
                <Btn size="sm" onClick={()=>setCreateMode(false)}>Отмена</Btn>
                <Btn size="sm" variant="primary" onClick={submit} disabled={!draft.name.trim()} icon={<Ic.check/>}>
                  Создать теплицу
                </Btn>
              </div>
              <div style={{gridColumn:'span 2',padding:'8px 10px',background:'var(--bg-sunken)',
                border:'1px dashed var(--line-strong)',borderRadius:6,
                fontSize:11,color:'var(--text-muted)',fontFamily:'var(--mono)'}}>
                POST /api/greenhouses → {'{ uid: "'}{uid}{'", name, timezone, greenhouse_type_id, description }'}
              </div>
            </div>
          )}
        </Card>

        <Card title="Зона выращивания"
          right={
            <div style={{display:'flex',gap:6}}>
              <Btn size="sm" variant={zn.mode==='select'?'primary':'secondary'} onClick={()=>setZn({...zn,mode:'select'})}>Выбрать</Btn>
              <Btn size="sm" variant={zn.mode==='create'?'primary':'secondary'} onClick={()=>setZn({...zn,mode:'create'})} icon={<Ic.plus/>}>Создать</Btn>
            </div>
          }>
          {zn.mode==='select' ? (
            <div style={{display:'grid',gridTemplateColumns:'1fr',gap:12}}>
              <Field label="Зона" required>
                <Select value={zn.zoneId} onChange={v=>setZn({...zn,zoneId:v})}
                  options={[
                    {value:'z-1',label:'Zone A · Tomato NFT · активна'},
                    {value:'z-4',label:'Zone Launch 2026-03-23T16-02-54-961Z · черновик'},
                    {value:'z-7',label:'Zone R&D · DWC · idle'},
                  ]} placeholder="— выберите —"/>
              </Field>
              <ZoneList activeId={zn.zoneId} onPick={v=>setZn({...zn,zoneId:v})}/>
            </div>
          ) : (
            <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:12}}>
              <Field label="Название зоны" required>
                <Input value={zn.name} onChange={v=>setZn({...zn,name:v})} placeholder="Zone Launch …"/>
              </Field>
              <Field label="Описание">
                <Input value={zn.desc} onChange={v=>setZn({...zn,desc:v})} placeholder="Front launch zone"/>
              </Field>
              <Field label="Площадь зоны"><Input value={zn.area} onChange={v=>setZn({...zn,area:v})} mono suffix="м²"/></Field>
              <Field label="Высота шкафа"><Input value={zn.h} onChange={v=>setZn({...zn,h:v})} mono suffix="см"/></Field>
            </div>
          )}
        </Card>
      </div>

      <div style={{display:'flex',flexDirection:'column',gap:12}}>
        <Hint show={hints}>
          Теплица — физическая группа зон с общим MQTT-бриджем и пулом ESP32-узлов.
          UID генерируется из названия (см. <span className="mono">generateUid()</span> в репо).
        </Hint>
        <Card title="Позиция в теплице">
          <StripePlaceholder w="100%" h={120} label="GH floor plan"/>
        </Card>
        <Card title="MQTT / Bridge" pad={true}>
          <KV rows={[
            ['MQTT host','host.docker.internal'],
            ['Bridge port','9000'],
            ['AE3','9405 online'],
            ['history-logger','online'],
          ]}/>
        </Card>
      </div>
    </div>
  );
}

// =================================================================
// STEP 2 — Рецепт-визард: select existing OR open RecipeEditor inline
// =================================================================
function Step2RecipeV2({ data, set, hints, recipes }){
  const mode = data.mode; // 'select' | 'create' | 'edit'
  return (
    <div style={{display:'grid',gridTemplateColumns:'1fr 360px',gap:16}}>
      <Card title="Рецепт"
        right={
          <div style={{display:'flex',gap:6}}>
            <Btn size="sm" variant={mode==='select'?'primary':'secondary'} onClick={()=>set({...data,mode:'select'})}>Выбрать</Btn>
            <Btn size="sm" variant={mode==='create'?'primary':'secondary'} onClick={()=>set({...data,mode:'create'})} icon={<Ic.plus/>}>Создать новый</Btn>
            {data.recipeId && mode!=='edit' && (
              <Btn size="sm" variant="secondary" onClick={()=>set({...data,mode:'edit'})} icon={<Ic.edit/>}>Редактировать</Btn>
            )}
          </div>
        }>
        {mode==='select' && <RecipeSelector data={data} set={set} recipes={recipes}/>}
        {(mode==='create' || mode==='edit') && (
          <RecipeEditor data={data} set={set} mode={mode}
            onCancel={()=>set({...data,mode:'select'})}
            onSave={()=>set({...data,mode:'select'})}/>
        )}
      </Card>

      <div style={{display:'flex',flexDirection:'column',gap:12}}>
        <Hint show={hints}>
          Целевые pH/EC, система выращивания и расписание — берутся из <b>рецепта</b>.
          На шаге «Автоматика» они только отображаются. Чтобы их изменить — отредактируйте рецепт.
        </Hint>
        <Card title="Активная ревизия" pad={true}>
          <KV rows={[
            ['recipeId',  data.recipeId || '—'],
            ['ревизия',   data.revisionNumber ? `r${data.revisionNumber}` : '—'],
            ['статус',    data.status || 'DRAFT'],
            ['всего фаз', data.phases?.length ?? 0],
          ]}/>
        </Card>
        <Card title="Превью фаз" pad={false}>
          <PhaseStrip phases={data.phases||[]}/>
        </Card>
      </div>
    </div>
  );
}

// ---------- Selector ----------
function RecipeSelector({ data, set, recipes }){
  const r = recipes.find(x => x.id === data.recipeId);
  const apply = (id) => {
    const rec = recipes.find(x=>x.id===id);
    if (!rec) return set({...data, recipeId:null, revisionNumber:null, phases:[], system:'', substrate:'',
                          targetPh:null, targetEc:null, status:'—', plantId:null});
    set({...data,
      recipeId: rec.id, revisionNumber: rec.revisionNumber,
      phases: rec.phases, system: rec.system, substrate: rec.substrate,
      targetPh: rec.targetPh, targetEc: rec.targetEc,
      status: rec.status, plantId: rec.plantId, name: rec.name,
      cycle: rec.phases.reduce((a,p)=>a+p.days,0),
    });
  };

  return (
    <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:12}}>
      <Field label="Рецепт" required>
        <Select value={data.recipeId??''} onChange={v=>apply(v?Number(v):null)}
          options={[{value:'',label:'— не выбран —'},
            ...recipes.map(r=>({value:String(r.id),label:`${r.name} · r${r.revisionNumber} · ${r.status}`}))]}/>
      </Field>
      <Field label="Дата посадки">
        <Input value={data.plantingAt} onChange={v=>set({...data,plantingAt:v})} mono/>
      </Field>
      <Field label="Батч">
        <Input value={data.batch} onChange={v=>set({...data,batch:v})} placeholder="batch-2026-03"/>
      </Field>
      <Field label="Цикл, дней" hint="из суммы фаз">
        <Input value={data.cycle||0} mono readOnly/>
      </Field>
      <div style={{gridColumn:'span 2',display:'grid',gridTemplateColumns:'repeat(4,1fr)',gap:10}}>
        <Stat label="Система"  value={data.system   || '—'}/>
        <Stat label="Субстрат" value={data.substrate|| '—'}/>
        <Stat label="targetPh" value={data.targetPh ?? '—'} mono/>
        <Stat label="targetEc" value={data.targetEc!=null?`${data.targetEc} mS/cm`:'—'} mono/>
      </div>
      {r && (
        <div style={{gridColumn:'span 2'}}>
          <PhaseStrip phases={r.phases} expanded/>
        </div>
      )}
    </div>
  );
}

// ---------- Editor (полноценный визард) ----------
function RecipeEditor({ data, set, mode, onCancel, onSave }){
  // Local working copy for editor
  const [wf, setWf] = useS12(()=>({
    name: data.name || (mode==='create' ? '' : data.name) || '',
    plantId: data.plantId || 'p-1',
    system: data.system || 'NFT',
    substrate: data.substrate || 'Rockwool',
    targetPh: data.targetPh ?? 5.8,
    targetEc: data.targetEc ?? 1.6,
    phases: data.phases?.length ? data.phases : [
      { name:'Germination', days:7,  ph:5.8, ec:0.8, lightOn:18, lightOff:6, irrigInterval:60, irrigDuration:60,
        npk:'A · 1.0', cal:'B · 0.5', mag:'C · 0.3', micro:'D · 0.1' },
      { name:'Vegetation',  days:21, ph:5.8, ec:1.6, lightOn:16, lightOff:8, irrigInterval:30, irrigDuration:120,
        npk:'A · 2.0', cal:'B · 1.0', mag:'C · 0.6', micro:'D · 0.2' },
      { name:'Flowering',   days:28, ph:6.0, ec:2.2, lightOn:12, lightOff:12, irrigInterval:30, irrigDuration:120,
        npk:'A · 3.0', cal:'B · 1.5', mag:'C · 0.9', micro:'D · 0.3' },
      { name:'Harvest',     days:14, ph:6.0, ec:1.4, lightOn:10, lightOff:14, irrigInterval:60, irrigDuration:90,
        npk:'A · 1.0', cal:'B · 0.5', mag:'C · 0.3', micro:'D · 0.1' },
    ],
  }));

  const upd = (k,v) => setWf(s=>({...s,[k]:v}));
  const updPhase = (i,k,v) => setWf(s=>({...s, phases: s.phases.map((p,idx)=> idx===i?{...p,[k]:v}:p)}));
  const addPhase = () => setWf(s=>({...s, phases:[...s.phases,
    { name:`Phase ${s.phases.length+1}`, days:7, ph:s.targetPh, ec:s.targetEc,
      lightOn:14, lightOff:10, irrigInterval:30, irrigDuration:120,
      npk:'A · 1.0', cal:'B · 0.5', mag:'C · 0.3', micro:'D · 0.1' }]}));
  const rmPhase = (i) => setWf(s=>({...s, phases: s.phases.filter((_,idx)=>idx!==i)}));

  const save = () => {
    const cycle = wf.phases.reduce((a,p)=>a+p.days,0);
    const newRevision = mode==='edit' ? (data.revisionNumber||1) + 1 : 1;
    set({
      ...data,
      mode:'select',
      recipeId: data.recipeId || ('r-' + Math.floor(Math.random()*1000)),
      revisionNumber: newRevision,
      status: mode==='edit' ? 'DRAFT (auto-publish)' : 'DRAFT',
      name: wf.name || 'Untitled recipe',
      plantId: wf.plantId,
      system: wf.system,
      substrate: wf.substrate,
      targetPh: Number(wf.targetPh),
      targetEc: Number(wf.targetEc),
      phases: wf.phases,
      cycle,
    });
    onSave();
  };

  return (
    <div style={{display:'flex',flexDirection:'column',gap:14}}>
      {mode==='edit' && data.usageCount>0 && (
        <div style={{padding:'8px 10px',border:'1px solid var(--warn)',borderRadius:6,
          background:'var(--warn-soft)',fontSize:12,color:'var(--text)'}}>
          ⚠ Рецепт активен в <b>{data.usageCount}</b> зон(е/ах). Сохранение создаст{' '}
          <b>новую DRAFT-ревизию</b> и опубликует её. Активные циклы продолжат работать
          на текущей PUBLISHED-версии до явного переключения через «Сменить ревизию» в зоне.
        </div>
      )}

      <SectionLabel12>Метаданные</SectionLabel12>
      <div style={{display:'grid',gridTemplateColumns:'1.4fr 1fr 1fr 1fr',gap:10}}>
        <Field label="Название рецепта" required>
          <Input value={wf.name} onChange={v=>upd('name',v)} placeholder="Tomato Launch r1"/>
        </Field>
        <Field label="Культура">
          <Select value={wf.plantId} onChange={v=>upd('plantId',v)} options={[
            {value:'p-1',label:'Tomato'}, {value:'p-2',label:'Lettuce'},
            {value:'p-3',label:'Basil'},  {value:'p-4',label:'Strawberry'},
          ]}/>
        </Field>
        <Field label="Система выращивания" required hint="будет читаться шагом 3">
          <Select value={wf.system} onChange={v=>upd('system',v)}
            options={['NFT','DWC','Drip · drip_tape','Drip · drip_emitter','Ebb & Flow','Aeroponics']}/>
        </Field>
        <Field label="Субстрат">
          <Select value={wf.substrate} onChange={v=>upd('substrate',v)}
            options={['Rockwool','Coco','Perlite','Hydroton','—']}/>
        </Field>
      </div>

      <SectionLabel12>Целевые pH / EC (для всего рецепта)</SectionLabel12>
      <div style={{display:'grid',gridTemplateColumns:'repeat(4,1fr)',gap:10}}>
        <Field label="targetPh" required>
          <Input value={wf.targetPh} onChange={v=>upd('targetPh',+v)} mono/>
        </Field>
        <Field label="targetEc" required>
          <Input value={wf.targetEc} onChange={v=>upd('targetEc',+v)} mono suffix="mS/cm"/>
        </Field>
        <Stat label="Сумма фаз" value={`${wf.phases.reduce((a,p)=>a+p.days,0)} дней`} mono/>
        <Stat label="Фаз" value={wf.phases.length} mono/>
      </div>

      <SectionLabel12 right={<Btn size="sm" icon={<Ic.plus/>} onClick={addPhase}>Добавить фазу</Btn>}>
        Фазы роста
      </SectionLabel12>

      <div style={{border:'1px solid var(--line)',borderRadius:6,overflow:'hidden'}}>
        <div style={{display:'grid',
          gridTemplateColumns:'1.3fr 60px 60px 70px 90px 90px 1fr 28px',
          padding:'8px 10px',background:'var(--bg-sunken)',
          fontSize:10,letterSpacing:'.05em',textTransform:'uppercase',color:'var(--text-faint)'}}>
          <span>Фаза</span><span>Дней</span><span>pH</span><span>EC</span>
          <span>Свет on/off</span><span>Полив i/d</span><span>Питание (A·B·C·D)</span><span></span>
        </div>
        {wf.phases.map((p,i)=>(
          <div key={i} style={{display:'grid',
            gridTemplateColumns:'1.3fr 60px 60px 70px 90px 90px 1fr 28px',
            gap:6,padding:'8px 10px',borderTop:'1px solid var(--line)',alignItems:'center'}}>
            <Input value={p.name} onChange={v=>updPhase(i,'name',v)}/>
            <Input value={p.days} onChange={v=>updPhase(i,'days',+v)} mono/>
            <Input value={p.ph} onChange={v=>updPhase(i,'ph',+v)} mono/>
            <Input value={p.ec} onChange={v=>updPhase(i,'ec',+v)} mono/>
            <span className="mono" style={{fontSize:11,color:'var(--text-muted)'}}>
              <input value={p.lightOn} onChange={e=>updPhase(i,'lightOn',+e.target.value)}
                style={{width:24,background:'transparent',border:0,color:'inherit',font:'inherit',textAlign:'right'}}/>/
              <input value={p.lightOff} onChange={e=>updPhase(i,'lightOff',+e.target.value)}
                style={{width:24,background:'transparent',border:0,color:'inherit',font:'inherit'}}/> ч
            </span>
            <span className="mono" style={{fontSize:11,color:'var(--text-muted)'}}>
              <input value={p.irrigInterval} onChange={e=>updPhase(i,'irrigInterval',+e.target.value)}
                style={{width:30,background:'transparent',border:0,color:'inherit',font:'inherit',textAlign:'right'}}/>м/
              <input value={p.irrigDuration} onChange={e=>updPhase(i,'irrigDuration',+e.target.value)}
                style={{width:30,background:'transparent',border:0,color:'inherit',font:'inherit'}}/>с
            </span>
            <div style={{display:'flex',gap:4,fontSize:10,fontFamily:'var(--mono)',color:'var(--text-muted)'}}>
              <span title={p.npk}>{p.npk}</span><span>·</span>
              <span title={p.cal}>{p.cal}</span><span>·</span>
              <span title={p.mag}>{p.mag}</span><span>·</span>
              <span title={p.micro}>{p.micro}</span>
            </div>
            <button onClick={()=>rmPhase(i)} style={{
              background:'transparent',border:0,color:'var(--alert)',cursor:'default',fontSize:14}}
              title="Удалить фазу">×</button>
          </div>
        ))}
      </div>

      <PhaseStrip phases={wf.phases}/>

      <div style={{display:'flex',justifyContent:'flex-end',gap:8,paddingTop:6}}>
        <Btn size="sm" onClick={onCancel}>Отмена</Btn>
        <Btn size="sm" variant="primary" icon={<Ic.check/>} onClick={save} disabled={!wf.name.trim()}>
          {mode==='edit' ? 'Сохранить ревизию' : 'Создать рецепт'}
        </Btn>
      </div>
    </div>
  );
}

// ---------- Phase strip (visual) ----------
function PhaseStrip({ phases, expanded }){
  if (!phases?.length) return (
    <div style={{padding:14,color:'var(--text-faint)',fontSize:12,textAlign:'center'}}>
      Фазы появятся после выбора или создания рецепта
    </div>
  );
  const total = phases.reduce((a,b)=>a+b.days,0);
  const colors = ['var(--growth-soft)','var(--brand-soft)','var(--warn-soft)','var(--bg-sunken)'];
  return (
    <div>
      <div style={{display:'flex',height:expanded?34:28,
        borderTop:'1px solid var(--line)',borderBottom:'1px solid var(--line)'}}>
        {phases.map((p,i)=>(
          <div key={i} style={{
            flex: p.days/total, padding:'6px 8px',
            background: colors[i%colors.length],
            borderRight: i<phases.length-1?'1px solid var(--line)':'none',
            fontSize:11,color:'var(--text-muted)',
            display:'flex',justifyContent:'space-between',alignItems:'center',gap:6,
            overflow:'hidden',whiteSpace:'nowrap',textOverflow:'ellipsis'}}>
            <span>{p.name}</span>
            <span className="mono" style={{fontSize:10}}>{p.days}д</span>
          </div>
        ))}
      </div>
      {expanded && (
        <div style={{display:'grid',gridTemplateColumns:`repeat(${phases.length},1fr)`}}>
          {phases.map((p,i)=>(
            <div key={i} style={{padding:'6px 10px',
              borderRight:i<phases.length-1?'1px solid var(--line)':'none',
              fontFamily:'var(--mono)',fontSize:11,color:'var(--text-muted)'}}>
              pH {p.ph} · EC {p.ec}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function SectionLabel12({ children, right }){
  return (
    <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',
      gap:8,paddingBottom:4,borderBottom:'1px dashed var(--line)'}}>
      <div style={{fontSize:11,letterSpacing:'.08em',textTransform:'uppercase',
        fontWeight:700,color:'var(--text-faint)'}}>{children}</div>
      {right}
    </div>
  );
}

Object.assign(window, { Step1ZoneV2, Step2RecipeV2 });
