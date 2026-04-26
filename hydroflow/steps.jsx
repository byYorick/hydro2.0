// Steps 1–5 of the launch wizard (aligned with ae3 GrowCycleLauncher manifest).
// 1 Зона   · select greenhouse → select/create zone
// 2 Рецепт · culture + recipe revision + phase preview
// 3 Автоматика · irrigation/pH/EC role bindings + ReadinessBar
// 4 Калибровка · hub: sensors · pumps · process · correction · pid
// 5 Подтверждение · diff-preview + launch
const { useState: useSt, useMemo: useM } = React;

const ROW_BORDER = { borderTop: '1px solid var(--line)' };

// ============================================================
// STEP 1 — Зона (greenhouse + zone)
// ============================================================
function Step1Zone({ gh, zn, setGh, setZn, hints }){
  const ghSummary = {
    'gh-01':{type:'Плёночная', area:420, zones:4, nodes:6, bridge:'9000'},
    'gh-02':{type:'Стеклянная', area:240, zones:2, nodes:3, bridge:'9000'},
    'gh-03':{type:'Контейнер',  area:80,  zones:1, nodes:2, bridge:'9000'},
  }[gh.greenhouseId];
  return (
    <div style={{display:'grid',gridTemplateColumns:'1fr 320px',gap:16}}>
      <div style={{display:'flex',flexDirection:'column',gap:12}}>
        <Card title="Теплица"
          right={<Chip tone={gh.greenhouseId?'growth':'warn'} icon={gh.greenhouseId?<Ic.check/>:<Ic.warn/>}>
            {gh.greenhouseId?gh.greenhouseId.toUpperCase():'не выбрана'}
          </Chip>}>
          <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:12}}>
            <Field label="Теплица" required>
              <Select value={gh.greenhouseId} onChange={v=>setGh({...gh,greenhouseId:v})}
                options={[
                  {value:'gh-01',label:'GH-01 · Berry · 420 м²'},
                  {value:'gh-02',label:'GH-02 · Leafy · 240 м²'},
                  {value:'gh-03',label:'GH-03 · R&D · 80 м²'},
                ]} placeholder="— выберите —"/>
            </Field>
            <Field label="Тип конструкции">
              <Select value={gh.ghType} onChange={v=>setGh({...gh,ghType:v})}
                options={['Плёночная','Стеклянная','Поликарбонат','Контейнер']}/>
            </Field>
            {ghSummary && (
              <div style={{gridColumn:'span 2',display:'grid',gridTemplateColumns:'100px 1fr',gap:14}}>
                <StripePlaceholder w={100} h={82} label="GH plan"/>
                <div style={{display:'grid',gridTemplateColumns:'repeat(4,1fr)',gap:10,alignContent:'center'}}>
                  <Stat label="Тип" value={ghSummary.type}/>
                  <Stat label="Площадь" value={`${ghSummary.area} м²`} mono/>
                  <Stat label="Зоны" value={ghSummary.zones} mono/>
                  <Stat label="Узлы online" value={`${ghSummary.nodes}/${ghSummary.nodes}`} mono tone="growth"/>
                </div>
              </div>
            )}
          </div>
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
              <div style={{gridColumn:'span 2'}}>
                <Field label="Схема циркуляции" hint="Определяет, какие контуры понадобятся на шаге «Автоматика»">
                  <Select value={zn.topology} onChange={v=>setZn({...zn,topology:v})}
                    options={['NFT · рециркуляция','DWC · барботаж','Капля · к слив','Ebb & Flow']}/>
                </Field>
              </div>
            </div>
          )}
        </Card>
      </div>

      <div style={{display:'flex',flexDirection:'column',gap:12}}>
        <Hint show={hints}>
          Теплица — физическая группа зон с общим MQTT-бриджем и пулом ESP32-узлов.
          Зона — минимальная единица автоматизации: свой grow-cycle, рецепт, контуры и PID.
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

function ZoneList({ activeId, onPick }){
  const rows = [
    {id:'z-1', name:'Zone A', plant:'Tomato «Cherry»', stage:'Vegetation d42', status:'active'},
    {id:'z-4', name:'Zone Launch 2026-03-23', plant:'—', stage:'черновик', status:'draft'},
    {id:'z-7', name:'Zone R&D', plant:'Basil', stage:'простаивает', status:'idle'},
  ];
  return (
    <div style={{border:'1px solid var(--line)',borderRadius:6,overflow:'hidden'}}>
      <div style={{display:'grid',gridTemplateColumns:'24px 1.4fr 1.2fr 1fr 90px',
        padding:'8px 12px',background:'var(--bg-sunken)',
        fontSize:11,color:'var(--text-faint)',textTransform:'uppercase',letterSpacing:'.05em'}}>
        <span/><span>Имя</span><span>Культура</span><span>Стадия</span><span>Статус</span>
      </div>
      {rows.map(r => (
        <div key={r.id} onClick={()=>onPick(r.id)}
          style={{display:'grid',gridTemplateColumns:'24px 1.4fr 1.2fr 1fr 90px',
            padding:'9px 12px',alignItems:'center',
            background: activeId===r.id?'var(--brand-soft)':'transparent',
            ...ROW_BORDER,cursor:'default'}}>
          <span>
            <span style={{display:'inline-block',width:10,height:10,borderRadius:'50%',
              background: activeId===r.id?'var(--brand)':'var(--line-strong)'}}/>
          </span>
          <span style={{fontWeight:500}}>{r.name}</span>
          <span style={{color:'var(--text-muted)'}}>{r.plant}</span>
          <span className="mono" style={{fontSize:12,color:'var(--text-muted)'}}>{r.stage}</span>
          <span>
            {r.status==='active' && <Chip tone="growth" icon={<Ic.dot/>}>активна</Chip>}
            {r.status==='draft' && <Chip tone="warn">черновик</Chip>}
            {r.status==='idle' && <Chip tone="neutral">idle</Chip>}
          </span>
        </div>
      ))}
    </div>
  );
}

// ============================================================
// STEP 2 — Рецепт и культура
// ============================================================
function Step2Recipe({ data, set, hints }){
  const mode = data.mode;
  return (
    <div style={{display:'grid',gridTemplateColumns:'1fr 360px',gap:16}}>
      <Card title="Культура и рецепт"
        right={
          <div style={{display:'flex',gap:6}}>
            <Btn size="sm" variant={mode==='select'?'primary':'secondary'} onClick={()=>set({...data,mode:'select'})}>Выбрать</Btn>
            <Btn size="sm" variant={mode==='create'?'primary':'secondary'} onClick={()=>set({...data,mode:'create'})} icon={<Ic.plus/>}>Создать</Btn>
          </div>
        }>
        {mode==='select' ? (
          <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:12}}>
            <Field label="Культура" required>
              <Select value={data.plantId} onChange={v=>set({...data,plantId:v})}
                options={[
                  {value:'p-1',label:'Tomato Launch — ревизия r3'},
                  {value:'p-2',label:'Lettuce Butterhead — r1'},
                  {value:'p-3',label:'Basil Genovese — r2'},
                ]} placeholder="— выберите —"/>
            </Field>
            <Field label="Ревизия рецепта" required>
              <Select value={data.recipeRev} onChange={v=>set({...data,recipeRev:v})}
                options={['r3 · актуальная','r2','r1']}/>
            </Field>
            <Field label="Дата посадки">
              <Input value={data.plantingAt} onChange={v=>set({...data,plantingAt:v})} mono
                prefix={<Ic.dot style={{color:'var(--brand)'}}/>}/>
            </Field>
            <Field label="Батч">
              <Input value={data.batch} onChange={v=>set({...data,batch:v})} placeholder="batch-2026-03"/>
            </Field>
            <div style={{gridColumn:'span 2'}}>
              <RecipePreview id={data.plantId}/>
            </div>
          </div>
        ) : (
          <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:12}}>
            <Field label="Название культуры" required>
              <Input value={data.name} onChange={v=>set({...data,name:v})} placeholder="Tomato Launch …"/>
            </Field>
            <Field label="Система выращивания" required>
              <Select value={data.system} onChange={v=>set({...data,system:v})}
                options={['NFT','DWC','Ebb & Flow','Drip']}/>
            </Field>
            <Field label="Субстрат">
              <Select value={data.substrate} onChange={v=>set({...data,substrate:v})}
                options={['Rockwool','Coco','Perlite','—']}/>
            </Field>
            <Field label="Ожид. цикл" hint="дней от посадки до финального сбора">
              <Input value={data.cycle} onChange={v=>set({...data,cycle:v})} mono suffix="дней"/>
            </Field>
            <div style={{gridColumn:'span 2',display:'grid',gridTemplateColumns:'repeat(4,1fr)',gap:12}}>
              <Field label="pH target"><Input value="5.8" mono/></Field>
              <Field label="EC target"><Input value="1.6" mono suffix="mS/cm"/></Field>
              <Field label="Свет"><Input value="16/8" mono/></Field>
              <Field label="Полив"><Input value="30 мин · 120 с" mono/></Field>
            </div>
          </div>
        )}
      </Card>
      <div style={{display:'flex',flexDirection:'column',gap:12}}>
        <Hint show={hints}>
          Рецепт — фазы роста с целями pH/EC, светом и поливом. На шаге «Калибровка» PID
          инициализируется из целей рецепта; переопределения локальны для этого запуска.
        </Hint>
        <Card title="Превью фазы" pad={false}>
          <div style={{padding:12,display:'flex',flexDirection:'column',gap:8}}>
            <div style={{display:'flex',gap:6,flexWrap:'wrap'}}>
              <Chip tone="growth">Germination</Chip>
              <Chip tone="growth">Vegetation</Chip>
              <Chip tone="neutral">→ Flowering</Chip>
              <Chip tone="neutral">→ Harvest</Chip>
            </div>
            <StripePlaceholder w="100%" h={100} label="фото культуры"/>
          </div>
        </Card>
      </div>
    </div>
  );
}

function RecipePreview({ id }){
  if (!id) return (
    <div style={{padding:14,border:'1px dashed var(--line-strong)',borderRadius:6,
      color:'var(--text-faint)',fontSize:12,textAlign:'center'}}>
      Выберите культуру, чтобы увидеть фазы рецепта
    </div>
  );
  const phases = [
    {name:'Germination', days:7,  ph:5.8, ec:0.8},
    {name:'Vegetation',  days:21, ph:5.8, ec:1.6},
    {name:'Flowering',   days:28, ph:6.0, ec:2.2},
    {name:'Harvest',     days:14, ph:6.0, ec:1.4},
  ];
  const total = phases.reduce((a,b)=>a+b.days,0);
  return (
    <div style={{border:'1px solid var(--line)',borderRadius:6,overflow:'hidden'}}>
      <div style={{display:'flex',height:28}}>
        {phases.map((p,i)=>(
          <div key={i} style={{
            flex: p.days/total, padding:'6px 8px',
            background: ['var(--growth-soft)','var(--brand-soft)','var(--warn-soft)','var(--bg-sunken)'][i],
            borderRight: i<phases.length-1?'1px solid var(--line)':'none',
            fontSize:11,color:'var(--text-muted)'}}>
            {p.name} · {p.days}д
          </div>
        ))}
      </div>
      <div style={{display:'grid',gridTemplateColumns:'repeat(4,1fr)'}}>
        {phases.map((p,i)=>(
          <div key={i} style={{padding:'8px 10px',borderRight:i<phases.length-1?'1px solid var(--line)':'none'}}>
            <div style={{fontSize:11,color:'var(--text-faint)'}}>pH / EC</div>
            <div className="mono" style={{fontSize:12}}>{p.ph} / {p.ec}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ============================================================
// STEP 3 — Автоматика (role bindings + readiness bar)
// ============================================================
function Step3Automation({ data, set, hints }){
  const rows = [
    {key:'irrigation', label:'Узел полива',       icon:<Ic.drop/>,   fragment:'Test: irrigation'},
    {key:'ph',         label:'Узел коррекции pH', icon:<Ic.beaker/>, fragment:'Test: pH correction'},
    {key:'ec',         label:'Узел коррекции EC', icon:<Ic.zap/>,    fragment:'Test: EC correction'},
  ];
  const bound = rows.filter(r => data[r.key]?.node && data[r.key]?.channel).length;
  return (
    <div style={{display:'flex',flexDirection:'column',gap:12}}>
      <AutomationReadinessBar bound={bound} total={rows.length}/>
      <div style={{display:'grid',gridTemplateColumns:'1fr 320px',gap:16}}>
        <Card title="Водно-солевой контур"
          right={<Chip tone="brand" icon={<Ic.chip/>}>6/6 узлов online</Chip>}>
          <div style={{display:'grid',gridTemplateColumns:'1fr',gap:10}}>
            {rows.map(r => (
              <div key={r.key} style={{display:'grid',gridTemplateColumns:'180px 1fr 1fr 110px',
                gap:10,alignItems:'end'}}>
                <div style={{display:'flex',alignItems:'center',gap:8,height:'var(--input-h)',
                  color:'var(--text-muted)',fontSize:13}}>
                  <span style={{color:'var(--brand)'}}>{r.icon}</span>{r.label}
                </div>
                <Field label="Узел (ESP32)">
                  <Select value={data[r.key]?.node} onChange={v=>set({...data,[r.key]:{...(data[r.key]||{}),node:v}})}
                    options={[
                      {value:'n-14',label:'Node-14 · irrigation-a'},
                      {value:'n-15',label:'Node-15 · dose-a'},
                      {value:'n-16',label:'Node-16 · dose-b'},
                    ]} placeholder="— выберите —" mono/>
                </Field>
                <Field label="Канал">
                  <Select value={data[r.key]?.channel} onChange={v=>set({...data,[r.key]:{...(data[r.key]||{}),channel:v}})}
                    options={[
                      {value:'ch-1',label:r.fragment},
                      {value:'ch-2',label:`Alt: ${r.key}-b`},
                    ]} placeholder="— выберите —" mono/>
                </Field>
                <div>
                  {data[r.key]?.node && data[r.key]?.channel
                    ? <Chip tone="growth" icon={<Ic.check/>}>связан</Chip>
                    : <Chip tone="warn">не задано</Chip>}
                </div>
              </div>
            ))}
          </div>
        </Card>
        <div style={{display:'flex',flexDirection:'column',gap:12}}>
          <Hint show={hints}>
            Команды узлам идут только через&nbsp;
            <span className="mono">history-logger → MQTT → ESP32</span>.
            Публикация напрямую из Laravel запрещена.
          </Hint>
          <Card title="Схема контура" pad={false}>
            <FlowDiagram/>
          </Card>
        </div>
      </div>
    </div>
  );
}

function AutomationReadinessBar({ bound, total }){
  const pct = Math.round((bound/total)*100);
  const tone = bound===total?'growth':'warn';
  return (
    <div style={{display:'flex',alignItems:'center',gap:14,padding:'10px 14px',
      background:'var(--bg-panel)',border:'1px solid var(--line)',borderRadius:8}}>
      <div style={{display:'flex',alignItems:'center',gap:8,minWidth:180}}>
        <Chip tone={tone} icon={bound===total?<Ic.check/>:<Ic.warn/>}>
          Автоматика <span className="mono">{bound}/{total}</span>
        </Chip>
      </div>
      <div style={{flex:1,height:6,background:'var(--bg-sunken)',borderRadius:999,overflow:'hidden'}}>
        <div style={{width:`${pct}%`,height:'100%',
          background: tone==='growth'?'var(--growth)':'var(--warn)'}}/>
      </div>
      <span className="mono" style={{fontSize:12,color:'var(--text-muted)'}}>{pct}%</span>
    </div>
  );
}

function FlowDiagram(){
  return (
    <svg viewBox="0 0 300 220" width="100%" style={{display:'block'}}>
      <defs>
        <marker id="arr" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto">
          <path d="M0 0 L10 5 L0 10 z" fill="currentColor"/>
        </marker>
      </defs>
      <g fill="none" stroke="var(--line-strong)" strokeWidth="1.2">
        <rect x="20" y="20" width="90" height="40" rx="4"/>
        <rect x="20" y="90" width="90" height="40" rx="4"/>
        <rect x="20" y="160" width="90" height="40" rx="4"/>
        <rect x="190" y="90" width="90" height="40" rx="4"/>
      </g>
      <g fill="var(--text-muted)" fontSize="10" fontFamily="var(--mono)">
        <text x="28" y="45">IRRIGATION</text>
        <text x="28" y="115">pH DOSE</text>
        <text x="28" y="185">EC DOSE</text>
        <text x="210" y="115">TANK</text>
      </g>
      <g fill="none" stroke="var(--brand)" strokeWidth="1.4" markerEnd="url(#arr)" style={{color:'var(--brand)'}}>
        <path d="M110 40 Q 150 40 150 90 L 190 110"/>
        <path d="M110 110 L 190 110"/>
        <path d="M110 180 Q 150 180 150 130 L 190 110"/>
      </g>
    </svg>
  );
}

// ============================================================
// STEP 4 — Калибровка (hub: sensors / pumps / process / correction / pid)
// ============================================================
function Step4Calibration({ data, set, hints, onOpenPumpWizard }){
  const [sub, setSub] = useSt('pumps');

  const pumpDone = data.pumps.filter(p=>p.status==='done').length;
  const pumpTotal = data.pumps.length;
  const pumpsBlocked = data.pumps.some(p=>p.status==='error');
  const pumpsOk = pumpDone===pumpTotal;

  const pidOk = data.pid.ph.saved && data.pid.ec.saved;
  const procDone = Object.values(data.proc).filter(Boolean).length;
  const procOk = procDone===4;

  // nav state per sidebar item
  const nav = {
    sensors:    { state:data.sensors.ph.ok && data.sensors.ec.ok ? 'passed' : 'active',
                  count: `${[data.sensors.ph.ok,data.sensors.ec.ok].filter(Boolean).length}/2` },
    pumps:      { state: pumpsOk?'passed':(pumpsBlocked?'blocker':'active'),
                  count:`${pumpDone}/${pumpTotal}` },
    process:    { state: pumpsOk ? (procOk?'passed':'active') : 'waiting',
                  count: `${procDone}/4`,
                  wait: !pumpsOk ? 'ждёт насосы' : '' },
    correction: { state: data.correction.saved?'passed':'optional', count:'опц.' },
    pid:        { state: pidOk?'passed':'optional', count:'опц.' },
  };

  // Readiness summary bar
  const blockersCount = [
    !pumpsOk && 'pumps',
    !(data.sensors.ph.ok && data.sensors.ec.ok) && 'sensors',
    !procOk && 'process',
  ].filter(Boolean).length;

  return (
    <div style={{display:'flex',flexDirection:'column',gap:12}}>
      <CalibrationReadinessBar blockers={blockersCount} nav={nav}/>
      <div style={{display:'grid',gridTemplateColumns:'240px 1fr',gap:12,alignItems:'start'}}>
        <CalSidebar current={sub} onPick={setSub} nav={nav}/>
        <div style={{background:'var(--bg-panel)',border:'1px solid var(--line)',borderRadius:8,
          padding:16,minHeight:360}}>
          {sub==='sensors'    && <SensorsSub    data={data} set={set} hints={hints}/>}
          {sub==='pumps'      && <PumpsSub      data={data} set={set} hints={hints} onOpen={onOpenPumpWizard}/>}
          {sub==='process'    && <ProcessSub    data={data} set={set} hints={hints}/>}
          {sub==='correction' && <CorrectionSub data={data} set={set} hints={hints}/>}
          {sub==='pid'        && <PidSub        data={data} set={set} hints={hints}/>}
        </div>
      </div>
    </div>
  );
}

function CalibrationReadinessBar({ blockers, nav }){
  const tone = blockers===0 ? 'growth' : 'warn';
  return (
    <div style={{display:'flex',alignItems:'center',gap:14,padding:'10px 14px',
      background:'var(--bg-panel)',border:'1px solid var(--line)',borderRadius:8}}>
      <Chip tone={tone} icon={blockers===0?<Ic.check/>:<Ic.warn/>}>
        Калибровка {blockers===0 ? 'готова' : `· ${blockers} блокер(а)`}
      </Chip>
      <span style={{width:1,height:20,background:'var(--line)'}}/>
      <div style={{display:'flex',gap:6,flexWrap:'wrap'}}>
        <Chip tone={nav.sensors.state==='passed'?'growth':'neutral'}>Сенсоры <span className="mono">{nav.sensors.count}</span></Chip>
        <Chip tone={nav.pumps.state==='passed'?'growth':(nav.pumps.state==='blocker'?'alert':'warn')}>Насосы <span className="mono">{nav.pumps.count}</span></Chip>
        <Chip tone={nav.process.state==='passed'?'growth':(nav.process.state==='waiting'?'neutral':'warn')}>
          Процесс <span className="mono">{nav.process.count}</span>{nav.process.wait?` · ${nav.process.wait}`:''}
        </Chip>
        <Chip tone="neutral">Коррекция · опц.</Chip>
        <Chip tone="neutral">PID · опц.</Chip>
      </div>
    </div>
  );
}

function CalSidebar({ current, onPick, nav }){
  const groups = [
    { title:'Базовая калибровка', items:[
      {id:'sensors', title:'Сенсоры', sub:'pH · EC · история', idx:1},
      {id:'pumps',   title:'Насосы',  sub:'дозирование · runtime', idx:2},
      {id:'process', title:'Процесс', sub:'окно · отклик · 4 фазы', idx:3},
    ]},
    { title:'Тонкая настройка', items:[
      {id:'correction', title:'Коррекция',      sub:'authority · пресеты'},
      {id:'pid',        title:'PID и autotune', sub:'доводка контура'},
    ]}
  ];
  return (
    <aside style={{display:'flex',flexDirection:'column',gap:14,padding:10,
      border:'1px solid var(--line)',borderRadius:8,background:'var(--bg-panel)'}}>
      {groups.map(g => (
        <div key={g.title} style={{display:'flex',flexDirection:'column',gap:2}}>
          <div style={{fontSize:10,letterSpacing:'.08em',textTransform:'uppercase',
            fontWeight:700,color:'var(--text-faint)',padding:'0 6px 4px'}}>{g.title}</div>
          {g.items.map(it => {
            const n = nav[it.id];
            const active = current===it.id;
            const stateBg = {
              passed:'var(--growth)', blocker:'var(--alert)',
              waiting:'var(--line-strong)', optional:'var(--line-strong)', active:'var(--brand)',
            }[n.state] || 'var(--line-strong)';
            const stateIcon = {
              passed:<Ic.check style={{color:'#fff'}}/>,
              blocker:<Ic.warn style={{color:'#fff'}}/>,
            }[n.state];
            return (
              <button key={it.id} onClick={()=>onPick(it.id)} style={{
                display:'flex',alignItems:'center',gap:8,padding:'8px 8px',
                border:0,borderRadius:6,cursor:'default',
                background: active?'var(--brand-soft)':'transparent',
                color: active?'var(--brand-ink)':'var(--text)',
                textAlign:'left',
              }}>
                <span style={{width:20,height:20,borderRadius:'50%',
                  display:'inline-flex',alignItems:'center',justifyContent:'center',
                  background: active?'var(--brand)':stateBg,color:'#fff'}}>
                  {stateIcon || <span className="mono" style={{fontSize:11,fontWeight:600}}>{it.idx||'·'}</span>}
                </span>
                <span style={{display:'flex',flexDirection:'column',lineHeight:1.2,flex:1,minWidth:0}}>
                  <span style={{fontSize:13,fontWeight:500,display:'flex',justifyContent:'space-between',gap:6}}>
                    {it.title}
                    <span className="mono" style={{fontSize:11,color:active?'var(--brand-ink)':'var(--text-faint)'}}>
                      {n.count}
                    </span>
                  </span>
                  <span style={{fontSize:11,color:'var(--text-faint)'}}>
                    {it.sub}{n.wait?` · ${n.wait}`:''}
                  </span>
                </span>
              </button>
            );
          })}
        </div>
      ))}
    </aside>
  );
}

// --- sub: Sensors --------------------------------------------------------
function SensorsSub({ data, set, hints }){
  const toggle = (k) => set({...data, sensors:{...data.sensors,[k]:{...data.sensors[k], ok:!data.sensors[k].ok, at: new Date().toISOString()}}});
  return (
    <div style={{display:'flex',flexDirection:'column',gap:14}}>
      <Head title="Калибровка сенсоров" sub="Отдельный контур для pH/EC проб и её история."/>
      <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:12}}>
        {['ph','ec'].map(k => {
          const s = data.sensors[k];
          return (
            <div key={k} style={{border:'1px solid var(--line)',borderRadius:6,padding:12,
              display:'flex',flexDirection:'column',gap:10}}>
              <div style={{display:'flex',alignItems:'center',justifyContent:'space-between'}}>
                <div style={{display:'flex',alignItems:'center',gap:8}}>
                  <span style={{color:'var(--brand)'}}>{k==='ph'?<Ic.beaker/>:<Ic.wave/>}</span>
                  <b style={{fontSize:13}}>{k.toUpperCase()}</b>
                  <span className="mono" style={{fontSize:11,color:'var(--text-faint)'}}>{s.sensor}</span>
                </div>
                {s.ok
                  ? <Chip tone="growth" icon={<Ic.check/>}>откалиброван</Chip>
                  : <Chip tone="warn">не откалиброван</Chip>}
              </div>
              <div style={{display:'grid',gridTemplateColumns:'repeat(3,1fr)',gap:8}}>
                <Stat label="Last value" value={s.value} mono/>
                <Stat label="Offset"    value={s.offset} mono/>
                <Stat label="Slope"     value={s.slope} mono/>
              </div>
              <div style={{fontSize:11,color:'var(--text-faint)',fontFamily:'var(--mono)'}}>
                {s.ok?`calibrated_at: ${s.at}`:'не калибровался'}
              </div>
              <div style={{display:'flex',gap:6,justifyContent:'flex-end'}}>
                <Btn size="sm">История</Btn>
                <Btn size="sm" variant="primary" icon={<Ic.check/>} onClick={()=>toggle(k)}>
                  {s.ok?'Перекалибровать':'Калибровать'}
                </Btn>
              </div>
            </div>
          );
        })}
      </div>
      <Hint show={hints}>
        Двухточечная калибровка буферами (pH 4.01 / 6.86, EC 1.413). AE3 сохраняет
        offset/slope и применяет их к каждому raw-значению из mqtt-bridge.
      </Hint>
    </div>
  );
}

// --- sub: Pumps ----------------------------------------------------------
function PumpsSub({ data, set, hints, onOpen }){
  const rows = data.pumps;
  const COLS = '1.1fr 1fr 80px 80px 90px 110px 110px';
  return (
    <div style={{display:'flex',flexDirection:'column',gap:12}}>
      <Head title="Дозирующие насосы" sub="6 компонентов дозации. Длительность 10 с, фактический объём — мензуркой."
        right={<Btn variant="primary" icon={<Ic.play/>} onClick={()=>onOpen(0)}>Открыть визард</Btn>}/>
      <div style={{border:'1px solid var(--line)',borderRadius:6,overflow:'hidden'}}>
        <div style={{display:'grid',gridTemplateColumns:COLS,padding:'8px 12px',
          background:'var(--bg-sunken)',fontSize:11,color:'var(--text-faint)',
          textTransform:'uppercase',letterSpacing:'.05em'}}>
          <span>Компонент</span><span>Канал</span><span>Длит.</span><span>Факт., мл</span>
          <span>мл/сек</span><span>Статус</span><span/>
        </div>
        {rows.map((r,i)=>(
          <div key={r.component} style={{display:'grid',gridTemplateColumns:COLS,
            padding:'8px 12px',alignItems:'center',...ROW_BORDER}}>
            <span style={{display:'flex',alignItems:'center',gap:8}}>
              <span className="mono" style={{fontSize:12,color:'var(--brand)'}}>{r.component}</span>
              <span style={{color:'var(--text-faint)',fontSize:11}}>{r.label}</span>
            </span>
            <span className="mono" style={{fontSize:12,color:'var(--text-muted)'}}>{r.channel}</span>
            <span className="mono" style={{fontSize:12}}>{r.duration}с</span>
            <span className="mono" style={{fontSize:12}}>{r.actualMl ?? '—'}</span>
            <span className="mono" style={{fontSize:12,color: r.rate?'var(--text)':'var(--text-faint)'}}>
              {r.rate ?? '—'}
            </span>
            <span>
              {r.status==='done' && <Chip tone="growth" icon={<Ic.check/>}>сохранено</Chip>}
              {r.status==='todo' && <Chip tone="warn">не откалиб.</Chip>}
              {r.status==='error' && <Chip tone="alert" icon={<Ic.warn/>}>ошибка</Chip>}
            </span>
            <span>
              <Btn size="sm" onClick={()=>onOpen(i)} icon={<Ic.edit/>}>
                {r.status==='done'?'Перекалибр.':'Калибровать'}
              </Btn>
            </span>
          </div>
        ))}
      </div>
      <Hint show={hints}>
        POST <span className="mono">/api/zones/{'{id}'}/calibrate-pump</span>&nbsp;·
        params <span className="mono">{`{node_channel_id, duration_sec, actual_ml, component, skip_run, manual_override}`}</span>.
      </Hint>
    </div>
  );
}

// --- sub: Process --------------------------------------------------------
function ProcessSub({ data, set, hints }){
  const modes = [
    {id:'solution_fill', label:'Наполнение'},
    {id:'tank_recirc',   label:'Рециркуляция'},
    {id:'irrigation',    label:'Полив'},
    {id:'generic',       label:'Generic'},
  ];
  const [m, setM] = useSt('solution_fill');
  const saved = data.proc[m];
  return (
    <div style={{display:'flex',flexDirection:'column',gap:12}}>
      <Head title="Калибровка процесса" sub="Окно наблюдения и коэффициенты отклика для 4 режимов работы."/>
      <div style={{display:'grid',gridTemplateColumns:'180px 1fr',gap:16}}>
        <div style={{display:'flex',flexDirection:'column',gap:4}}>
          {modes.map(x => (
            <button key={x.id} onClick={()=>setM(x.id)}
              style={{display:'flex',alignItems:'center',justifyContent:'space-between',
                padding:'8px 10px',border:0,background: m===x.id?'var(--brand-soft)':'transparent',
                color: m===x.id?'var(--brand-ink)':'var(--text)',borderRadius:6,cursor:'default'}}>
              <span>{x.label}</span>
              {data.proc[x.id] ? <Ic.check style={{color:'var(--growth)'}}/> : <span style={{fontSize:11,color:'var(--text-faint)'}}>—</span>}
            </button>
          ))}
        </div>
        <div>
          <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',marginBottom:10}}>
            <div style={{fontSize:13,fontWeight:600}}>Коэффициенты <span className="mono" style={{color:'var(--text-muted)'}}>{m}</span></div>
            {saved ? <Chip tone="growth" icon={<Ic.check/>}>сохранено</Chip> : <Chip tone="warn">не сохранено</Chip>}
          </div>
          <div style={{display:'grid',gridTemplateColumns:'repeat(3,1fr)',gap:10}}>
            <Field label="ec_gain_per_ml"><Input value="0.11" mono/></Field>
            <Field label="ph_up_gain_per_ml"><Input value="0.08" mono/></Field>
            <Field label="ph_down_gain_per_ml"><Input value="0.07" mono/></Field>
            <Field label="ph_per_ec_ml"><Input value="-0.015" mono/></Field>
            <Field label="ec_per_ph_ml"><Input value="0.02" mono/></Field>
            <Field label="confidence"><Input value="0.75" mono/></Field>
            <Field label="transport_delay"><Input value="20" mono suffix="с"/></Field>
            <Field label="settle"><Input value="45" mono suffix="с"/></Field>
          </div>
          <div style={{display:'flex',justifyContent:'flex-end',gap:6,marginTop:14}}>
            <Btn>Сбросить по умолчанию</Btn>
            <Btn variant="primary" icon={<Ic.check/>} onClick={()=>set({...data,proc:{...data.proc,[m]:true}})}>
              Сохранить «{modes.find(x=>x.id===m).label}»
            </Btn>
          </div>
          <div style={{marginTop:14}}>
            <Hint show={hints}>
              PUT <span className="mono">/api/zones/{'{id}'}/process-calibrations/{'{mode}'}</span>.
              Коэффициенты определяют, как AE3 прогнозирует реакцию раствора на дозу.
            </Hint>
          </div>
        </div>
      </div>
    </div>
  );
}

// --- sub: Correction -----------------------------------------------------
function CorrectionSub({ data, set, hints }){
  const d = data.correction;
  const save = ()=> set({...data, correction:{...d, saved:true}});
  return (
    <div style={{display:'flex',flexDirection:'column',gap:12}}>
      <Head title="Конфигурация коррекции"
        sub="Authority-редактор: база / переопределения / жизненный цикл пресетов / сравнение."/>
      <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:16}}>
        <div>
          <div style={{fontSize:11,color:'var(--text-faint)',textTransform:'uppercase',
            letterSpacing:'.05em',marginBottom:6}}>Authority</div>
          <div style={{display:'flex',gap:6,marginBottom:12}}>
            {['recipe','zone','manual'].map(a=>(
              <Btn key={a} size="sm" variant={d.authority===a?'primary':'secondary'}
                onClick={()=>set({...data,correction:{...d,authority:a,saved:false}})}>{a}</Btn>
            ))}
          </div>
          <div style={{display:'grid',gridTemplateColumns:'repeat(2,1fr)',gap:10}}>
            <Field label="max_step_ml"><Input value={d.max_step_ml} mono/></Field>
            <Field label="step_interval"><Input value={d.step_interval} mono suffix="с"/></Field>
            <Field label="cooldown"><Input value={d.cooldown} mono suffix="с"/></Field>
            <Field label="tolerance_ph"><Input value={d.tol_ph} mono/></Field>
            <Field label="tolerance_ec"><Input value={d.tol_ec} mono/></Field>
            <Field label="dry_run"><Select value={d.dry_run} options={['false','true']}/></Field>
          </div>
        </div>
        <div>
          <div style={{fontSize:11,color:'var(--text-faint)',textTransform:'uppercase',
            letterSpacing:'.05em',marginBottom:6}}>Пресет vs. текущее</div>
          <div style={{border:'1px solid var(--line)',borderRadius:6,overflow:'hidden'}}>
            {[
              ['authority','recipe','zone'],
              ['max_step_ml','3.0','5.0'],
              ['step_interval','60','90'],
              ['cooldown','120','180'],
            ].map((r,i)=>(
              <div key={i} style={{display:'grid',gridTemplateColumns:'1.2fr 1fr 1fr',
                padding:'8px 12px',gap:8,alignItems:'center',
                ...(i>0?ROW_BORDER:{}),
                background: i===0?'var(--bg-sunken)':'transparent'}}>
                <span style={{fontSize:12,color: i===0?'var(--text-faint)':'var(--text-muted)',
                  textTransform: i===0?'uppercase':'none',letterSpacing:i===0?'.05em':0}}>
                  {i===0?'Параметр':r[0]}
                </span>
                <span className="mono" style={{fontSize:12,color:i===0?'var(--text-faint)':'var(--text-faint)'}}>{r[1]}</span>
                <span className="mono" style={{fontSize:12,color:i===0?'var(--text-faint)':'var(--brand-ink)'}}>{r[2]}</span>
              </div>
            ))}
          </div>
          <div style={{display:'flex',gap:6,justifyContent:'flex-end',marginTop:14}}>
            <Btn>Сбросить</Btn>
            <Btn variant="primary" icon={<Ic.check/>} onClick={save}>Сохранить</Btn>
          </div>
          <div style={{marginTop:12}}>
            <Hint show={hints}>
              Коррекция — опциональный шаг тонкой настройки, можно пропустить.
              PUT <span className="mono">/api/automation-configs/zone/{'{id}'}/zone.correction</span>.
            </Hint>
          </div>
        </div>
      </div>
    </div>
  );
}

// --- sub: PID (ex. Step 5 PID tab) --------------------------------------
function PidSub({ data, set, hints }){
  const [t, setT] = useSt('ph');
  const pid = data.pid[t];
  const save = () => set({...data, pid:{...data.pid, [t]:{...pid, saved:true}}});
  return (
    <div style={{display:'flex',flexDirection:'column',gap:12}}>
      <Head title="PID и автонастройка" sub="Доводка контура коррекции. Открывайте только после базовой калибровки."/>
      <div style={{display:'grid',gridTemplateColumns:'1fr 320px',gap:16}}>
        <div>
          <div style={{display:'flex',gap:6,marginBottom:10}}>
            <Btn size="sm" variant={t==='ph'?'primary':'secondary'} onClick={()=>setT('ph')}>pH</Btn>
            <Btn size="sm" variant={t==='ec'?'primary':'secondary'} onClick={()=>setT('ec')}>EC</Btn>
            <div style={{flex:1}}/>
            {pid.saved ? <Chip tone="growth" icon={<Ic.check/>}>сохранено</Chip> : <Chip tone="warn">не сохранено</Chip>}
          </div>
          <div style={{display:'grid',gridTemplateColumns:'repeat(4,1fr)',gap:10}}>
            <Field label="Target"><Input value={pid.target} mono onChange={v=>set({...data,pid:{...data.pid,[t]:{...pid,target:v,saved:false}}})}/></Field>
            <Field label="Dead zone"><Input value={pid.dead_zone} mono/></Field>
            <Field label="Close zone"><Input value={pid.close_zone} mono/></Field>
            <Field label="Far zone"><Input value={pid.far_zone} mono/></Field>
          </div>
          <div style={{marginTop:14,border:'1px solid var(--line)',borderRadius:6,overflow:'hidden'}}>
            <div style={{display:'grid',gridTemplateColumns:'80px repeat(3,1fr)',
              background:'var(--bg-sunken)',padding:'8px 12px',fontSize:11,
              color:'var(--text-faint)',textTransform:'uppercase',letterSpacing:'.05em'}}>
              <span>Зона</span><span>Kp</span><span>Ki</span><span>Kd</span>
            </div>
            {['close','far'].map(z=>(
              <div key={z} style={{display:'grid',gridTemplateColumns:'80px repeat(3,1fr)',
                padding:'8px 12px',alignItems:'center',gap:8,...ROW_BORDER}}>
                <span className="mono" style={{fontSize:12,color:'var(--text-muted)'}}>{z}</span>
                {['kp','ki','kd'].map(k=>(
                  <Input key={k} value={pid.zone_coeffs[z][k]} mono/>
                ))}
              </div>
            ))}
          </div>
          <div style={{display:'grid',gridTemplateColumns:'repeat(3,1fr)',gap:10,marginTop:14}}>
            <Field label="Max output"><Input value={pid.max_output} mono/></Field>
            <Field label="Min interval" hint="мс"><Input value={pid.min_interval_ms} mono suffix="мс"/></Field>
            <Field label="Max integral"><Input value={pid.max_integral} mono/></Field>
          </div>
          <div style={{display:'flex',justifyContent:'flex-end',gap:6,marginTop:14}}>
            <Btn>Autotune</Btn>
            <Btn variant="primary" onClick={save} icon={<Ic.check/>}>Сохранить {t.toUpperCase()}</Btn>
          </div>
        </div>
        <div style={{display:'flex',flexDirection:'column',gap:12}}>
          <Card title="Зона регулирования" pad={false}>
            <PidChart target={+pid.target} dead={+pid.dead_zone} close={+pid.close_zone} far={+pid.far_zone} label={t}/>
          </Card>
          <Hint show={hints}>
            Dead / close / far — пороговые отклонения от target. PID переключает
            коэффициенты (close/far) в зависимости от зоны измерения.
          </Hint>
        </div>
      </div>
    </div>
  );
}

function PidChart({ target, dead, close, far, label }){
  const W = 300, H = 140, cx = W/2;
  const band = (v, color) => (
    <rect x={cx - (W*0.45)*(v/far)} width={(W*0.45)*2*(v/far)} y={20} height={H-40}
      fill={color} opacity="0.3"/>
  );
  return (
    <div style={{padding:12}}>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%">
        {band(far,'var(--alert-soft)')}
        {band(close,'var(--warn-soft)')}
        {band(dead,'var(--growth-soft)')}
        <line x1={cx} x2={cx} y1="10" y2={H-10} stroke="var(--brand)" strokeWidth="1.2"/>
        <g fontFamily="var(--mono)" fontSize="10" fill="var(--text-muted)">
          <text x={cx+4} y="18">target {target}</text>
          <text x="6" y={H-4}>{label==='ph'?'pH':'EC'} −{far}</text>
          <text x={W-40} y={H-4}>+{far}</text>
        </g>
      </svg>
    </div>
  );
}

// ============================================================
// STEP 5 — Подтверждение (diff-preview + launch)
// ============================================================
function Step5Preview({ snap, readiness, diff, hints, onLaunch }){
  const ready = readiness.every(r => r.status==='ok');
  return (
    <div style={{display:'grid',gridTemplateColumns:'1.3fr 1fr',gap:16}}>
      <div style={{display:'flex',flexDirection:'column',gap:12}}>
        <Card title="Сводка запуска"
          right={ready
            ? <Chip tone="growth" icon={<Ic.check/>}>готова</Chip>
            : <Chip tone="warn" icon={<Ic.warn/>}>есть замечания</Chip>}>
          <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:14}}>
            <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:10}}>
              <Stat label="Теплица" value={snap.gh} icon={<Ic.gh/>}/>
              <Stat label="Зона" value={snap.zone} icon={<Ic.grid/>}/>
              <Stat label="Культура" value={snap.plant} icon={<Ic.leaf/>}/>
              <Stat label="Система" value={snap.system} mono/>
              <Stat label="pH target" value={snap.ph} mono tone="brand"/>
              <Stat label="EC target" value={snap.ec} mono tone="brand"/>
              <Stat label="Полив" value={snap.irrig} mono/>
              <Stat label="Ожид. урожай" value={snap.harvest} mono/>
            </div>
            <div>
              <div style={{fontSize:11,color:'var(--text-faint)',textTransform:'uppercase',
                letterSpacing:'.05em',marginBottom:6}}>Контуры</div>
              <div style={{display:'flex',flexDirection:'column',gap:6}}>
                <ContourRow icon={<Ic.drop/>} label="Полив" node="Node-14 · irrigation-a"/>
                <ContourRow icon={<Ic.beaker/>} label="pH" node="Node-15 · pump_base/pump_acid"/>
                <ContourRow icon={<Ic.zap/>} label="EC" node="Node-16 · pump_a…pump_d"/>
              </div>
            </div>
          </div>
        </Card>
        <Card title="Diff · zone.logic_profile"
          right={<Chip tone="brand" icon={<Ic.wave/>}>{diff.length} изменений</Chip>}>
          <DiffTable rows={diff}/>
        </Card>
      </div>
      <div style={{display:'flex',flexDirection:'column',gap:12}}>
        <Card title="Readiness check">
          <div style={{display:'flex',flexDirection:'column',gap:6}}>
            {readiness.map(r => <ReadinessRow key={r.key} {...r}/>)}
          </div>
        </Card>
        <LaunchCard ready={ready} onLaunch={onLaunch}/>
        <Hint show={hints}>
          POST <span className="mono">/api/zones/{'{id}'}/grow-cycles</span> с overrides.
          AE3 создаёт цикл, инициализирует стартовую фазу и планирует первый полив
          через scheduler-dispatch.
        </Hint>
      </div>
    </div>
  );
}

function DiffTable({ rows }){
  return (
    <div style={{border:'1px solid var(--line)',borderRadius:6,overflow:'hidden'}}>
      <div style={{display:'grid',gridTemplateColumns:'24px 1.4fr 1fr 1fr',
        padding:'8px 12px',background:'var(--bg-sunken)',
        fontSize:11,color:'var(--text-faint)',textTransform:'uppercase',letterSpacing:'.05em'}}>
        <span/><span>Путь</span><span>Текущее</span><span>Новое</span>
      </div>
      {rows.map((r,i)=>(
        <div key={i} style={{display:'grid',gridTemplateColumns:'24px 1.4fr 1fr 1fr',
          padding:'7px 12px',alignItems:'center',...ROW_BORDER}}>
          <span>
            <span style={{display:'inline-block',width:8,height:8,borderRadius:2,
              background: r.op==='add'?'var(--growth)':(r.op==='remove'?'var(--alert)':'var(--warn)')}}/>
          </span>
          <span className="mono" style={{fontSize:11,color:'var(--text-muted)'}}>{r.path}</span>
          <span className="mono" style={{fontSize:12,color:'var(--text-faint)',textDecoration: r.op==='replace'?'line-through':'none'}}>
            {r.from ?? '—'}
          </span>
          <span className="mono" style={{fontSize:12,color:'var(--brand-ink)'}}>{r.to ?? '—'}</span>
        </div>
      ))}
    </div>
  );
}

function ReadinessRow({ label, status, note }){
  const cfg = {
    ok:{ic:<Ic.check style={{color:'var(--growth)'}}/>},
    warn:{ic:<Ic.warn style={{color:'var(--warn)'}}/>},
    err:{ic:<Ic.x style={{color:'var(--alert)'}}/>},
  }[status];
  return (
    <div style={{display:'flex',alignItems:'center',gap:8,padding:'6px 0',
      borderBottom:'1px solid var(--line)'}}>
      <span style={{width:16,display:'inline-flex'}}>{cfg.ic}</span>
      <span style={{flex:1,fontSize:13}}>{label}</span>
      {note && <span style={{fontSize:11,color:'var(--text-faint)'}} className="mono">{note}</span>}
    </div>
  );
}

function LaunchCard({ ready, onLaunch }){
  return (
    <div style={{border:'1px solid var(--line)',borderRadius:8,overflow:'hidden',
      background:'linear-gradient(180deg, var(--bg-panel), var(--brand-soft))'}}>
      <div style={{padding:16,display:'flex',flexDirection:'column',gap:10}}>
        <div style={{fontSize:11,color:'var(--brand-ink)',textTransform:'uppercase',letterSpacing:'.08em',fontWeight:600}}>
          Запуск цикла
        </div>
        <div style={{fontSize:20,lineHeight:1.2,fontWeight:600,color:'var(--text)'}}>
          Готово. Посадка сейчас,<br/>первый полив через 00:30.
        </div>
        <div style={{display:'flex',gap:8,alignItems:'center'}}>
          <Btn variant="growth" size="lg" icon={<Ic.play/>} disabled={!ready} onClick={onLaunch}>
            Запустить цикл
          </Btn>
          <Btn size="lg">Симуляция</Btn>
        </div>
      </div>
    </div>
  );
}

function ContourRow({ icon, label, node }){
  return (
    <div style={{display:'flex',alignItems:'center',gap:8,padding:'6px 10px',
      border:'1px solid var(--line)',borderRadius:6,background:'var(--bg-sunken)'}}>
      <span style={{color:'var(--brand)'}}>{icon}</span>
      <span style={{fontSize:13,width:70}}>{label}</span>
      <span className="mono" style={{fontSize:12,color:'var(--text-muted)',flex:1}}>{node}</span>
      <Chip tone="growth" icon={<Ic.dot/>}>online</Chip>
    </div>
  );
}

// ============================================================
// Small atoms
// ============================================================
function Head({ title, sub, right }){
  return (
    <div style={{display:'flex',alignItems:'flex-start',justifyContent:'space-between',gap:10}}>
      <div>
        <div style={{fontSize:15,fontWeight:600}}>{title}</div>
        <div style={{fontSize:12,color:'var(--text-muted)',marginTop:2}}>{sub}</div>
      </div>
      {right}
    </div>
  );
}
function Stat({ label, value, mono, tone, icon }){
  const color = tone==='brand'?'var(--brand-ink)':tone==='growth'?'var(--growth)':'var(--text)';
  return (
    <div>
      <div style={{fontSize:11,color:'var(--text-faint)',textTransform:'uppercase',letterSpacing:'.05em',
        display:'flex',alignItems:'center',gap:4}}>
        {icon}{label}
      </div>
      <div className={mono?'mono':''} style={{fontSize:14,fontWeight:500,color}}>{value}</div>
    </div>
  );
}
function KV({ rows }){
  return (
    <div style={{display:'grid',gridTemplateColumns:'1fr auto',rowGap:6,columnGap:10,fontSize:12}}>
      {rows.map((r,i)=>(
        <React.Fragment key={i}>
          <span style={{color:'var(--text-faint)'}}>{r[0]}</span>
          <span className="mono" style={{color:'var(--text)'}}>{r[1]}</span>
        </React.Fragment>
      ))}
    </div>
  );
}

// ============================================================
// Pump calibration modal
// ============================================================
function PumpCalibrationModal({ open, data, idx, set, onClose }){
  if (!open) return null;
  const pump = data.pumps[idx];
  const update = (k,v)=> {
    set({...data, pumps: data.pumps.map((p,i)=> i===idx?{...p,[k]:v}:p)});
  };
  const save = ()=>{
    const rate = pump.actualMl && pump.duration ? (pump.actualMl/pump.duration).toFixed(3) : null;
    set({...data, pumps: data.pumps.map((p,i)=> i===idx?{...p, rate, status:'done'}:p)});
    onClose();
  };
  return (
    <div role="dialog" style={modalStyle.overlay}>
      <div style={modalStyle.panel}>
        <header style={modalStyle.head}>
          <div style={{display:'flex',alignItems:'center',gap:8}}>
            <Ic.beaker style={{color:'var(--brand)'}}/>
            <b style={{fontSize:14}}>Калибровка дозирующих насосов</b>
          </div>
          <button onClick={onClose} style={modalStyle.x}><Ic.x/></button>
        </header>
        <div style={{padding:16,display:'grid',gridTemplateColumns:'1fr 1fr',gap:14}}>
          <Field label="Компонент" required>
            <Select value={pump.component}
              options={data.pumps.map(p=>({value:p.component,label:`${p.component} · ${p.label}`}))}
              mono/>
          </Field>
          <Field label="Канал" required>
            <Select value={pump.channel} options={[pump.channel]} mono/>
          </Field>
          <Field label="Длительность" required>
            <Input value={pump.duration} onChange={v=>update('duration',v)} mono suffix="с"/>
          </Field>
          <Field label="Фактический объём" required hint="Измерьте мензуркой после прогонки">
            <Input value={pump.actualMl??''} onChange={v=>update('actualMl',v)} mono suffix="мл"/>
          </Field>
          <div style={{gridColumn:'span 2',display:'grid',gridTemplateColumns:'1fr 1fr 1fr',gap:10,
            padding:'10px 12px',background:'var(--bg-sunken)',border:'1px dashed var(--line-strong)',borderRadius:6}}>
            <Stat label="Расчётный расход" mono tone="brand"
              value={pump.actualMl && pump.duration ? `${(pump.actualMl/pump.duration).toFixed(3)} мл/с` : '—'}/>
            <Stat label="skip_run" value="true" mono/>
            <Stat label="manual_override" value="true" mono/>
          </div>
          <div style={{gridColumn:'span 2',display:'flex',justifyContent:'space-between',gap:8}}>
            <Btn icon={<Ic.play/>}>Прогнать 10 с</Btn>
            <div style={{display:'flex',gap:6}}>
              <Btn onClick={onClose}>Отмена</Btn>
              <Btn variant="primary" icon={<Ic.check/>} onClick={save}>Сохранить</Btn>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
const modalStyle = {
  overlay:{position:'fixed',inset:0,background:'rgba(10,20,28,.5)',
    display:'flex',alignItems:'center',justifyContent:'center',zIndex:1000,
    backdropFilter:'blur(2px)'},
  panel:{width:640,background:'var(--bg-panel)',border:'1px solid var(--line)',
    borderRadius:8,boxShadow:'0 20px 60px rgba(0,0,0,.25)'},
  head:{display:'flex',alignItems:'center',justifyContent:'space-between',
    padding:'12px 14px',borderBottom:'1px solid var(--line)'},
  x:{width:28,height:28,border:'1px solid var(--line)',borderRadius:6,background:'var(--bg-panel)',
    display:'inline-flex',alignItems:'center',justifyContent:'center',cursor:'default'},
};

Object.assign(window, {
  Step1Zone, Step2Recipe, Step3Automation, Step4Calibration, Step5Preview,
  PumpCalibrationModal, Stat, KV,
});
