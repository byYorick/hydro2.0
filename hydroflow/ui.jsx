// Core UI primitives for Hydroflow wizard.
const { useState, useEffect, useRef, useMemo } = React;

// --- TopBar --------------------------------------------------------------
function TopBar({ zoneName, onSwitchStepper, stepper }) {
  return (
    <header style={topBarStyle.root}>
      <div style={topBarStyle.left}>
        <div style={topBarStyle.logo}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
            <path d="M12 3c3 4 7 7 7 11a7 7 0 01-14 0c0-4 4-7 7-11z" stroke="var(--brand)" strokeWidth="1.6" strokeLinejoin="round"/>
            <path d="M12 9v7" stroke="var(--growth)" strokeWidth="1.6" strokeLinecap="round"/>
            <path d="M9.5 12l2.5 2 2.5-2" stroke="var(--growth)" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
          <b style={{fontWeight:600, letterSpacing:'-0.01em'}}>Hydroflow</b>
          <span style={topBarStyle.dim}>· v2.0·ae3</span>
        </div>
        <nav style={topBarStyle.nav}>
          <span style={topBarStyle.crumb}>Теплицы</span>
          <span style={topBarStyle.crumbSep}>/</span>
          <span style={topBarStyle.crumb}>GH-01 Berry</span>
          <span style={topBarStyle.crumbSep}>/</span>
          <span style={{...topBarStyle.crumb, color:'var(--text)'}}>Мастер запуска</span>
        </nav>
      </div>
      <div style={topBarStyle.right}>
        <span style={topBarStyle.pill}><Ic.dot style={{color:'var(--growth)'}}/> AE3 online</span>
        <span style={topBarStyle.pill}><span className="mono">agronomist@example.com</span></span>
      </div>
    </header>
  );
}
const topBarStyle = {
  root:{display:'flex',alignItems:'center',justifyContent:'space-between',
    padding:'0 20px',height:48,borderBottom:'1px solid var(--line)',
    background:'var(--bg-panel)',position:'sticky',top:0,zIndex:10},
  left:{display:'flex',alignItems:'center',gap:20},
  logo:{display:'flex',alignItems:'center',gap:8,fontSize:14},
  dim:{color:'var(--text-faint)',fontSize:12},
  nav:{display:'flex',alignItems:'center',gap:6,fontSize:12},
  crumb:{color:'var(--text-muted)'},
  crumbSep:{color:'var(--text-faint)'},
  right:{display:'flex',alignItems:'center',gap:10},
  pill:{display:'inline-flex',alignItems:'center',gap:6,padding:'4px 10px',
    border:'1px solid var(--line)',borderRadius:999,fontSize:12,color:'var(--text-muted)',
    background:'var(--bg-panel)'},
};

// --- Horizontal Stepper --------------------------------------------------
function HStepper({ steps, active, setActive, completion }) {
  return (
    <div style={hsStyle.root}>
      {steps.map((s, i) => {
        const state = completion[i]; // 'done' | 'current' | 'todo' | 'warn'
        const isActive = i === active;
        const realState = isActive ? 'current' : state;
        return (
          <React.Fragment key={s.id}>
            <button
              onClick={() => setActive(i)}
              style={{
                ...hsStyle.step,
                color: realState === 'todo' ? 'var(--text-faint)' : 'var(--text)',
              }}
            >
              <span style={{
                ...hsStyle.bullet,
                ...(realState === 'done' ? hsStyle.bulletDone : {}),
                ...(realState === 'current' ? hsStyle.bulletCurrent : {}),
                ...(realState === 'warn' ? hsStyle.bulletWarn : {}),
              }}>
                {realState === 'done' ? <Ic.check style={{color:'#fff'}}/> :
                 realState === 'warn' ? <Ic.warn style={{color:'#fff'}}/> :
                 <span className="mono" style={{fontSize:11,fontWeight:600}}>{i+1}</span>}
              </span>
              <span style={hsStyle.labels}>
                <span style={hsStyle.label}>{s.label}</span>
                <span style={hsStyle.sub}>{s.sub}</span>
              </span>
            </button>
            {i < steps.length - 1 && (
              <span style={{...hsStyle.bar,
                background: completion[i] === 'done' ? 'var(--brand)' : 'var(--line)'}}/>
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
}
const hsStyle = {
  root:{display:'flex',alignItems:'center',gap:0,
    padding:'14px 20px',borderBottom:'1px solid var(--line)',
    background:'var(--bg-panel)',overflowX:'auto'},
  step:{display:'flex',alignItems:'center',gap:10,padding:'6px 10px',
    background:'transparent',border:0,cursor:'default',whiteSpace:'nowrap',
    borderRadius:6},
  bullet:{width:22,height:22,minWidth:22,borderRadius:'50%',
    display:'inline-flex',alignItems:'center',justifyContent:'center',
    border:'1px solid var(--line-strong)',background:'var(--bg-panel)',
    color:'var(--text-muted)'},
  bulletDone:{background:'var(--brand)',borderColor:'var(--brand)',color:'#fff'},
  bulletCurrent:{borderColor:'var(--brand)',color:'var(--brand)',
    boxShadow:'0 0 0 3px var(--brand-soft)'},
  bulletWarn:{background:'var(--warn)',borderColor:'var(--warn)',color:'#fff'},
  labels:{display:'flex',flexDirection:'column',lineHeight:1.15,textAlign:'left'},
  label:{fontSize:13,fontWeight:500},
  sub:{fontSize:11,color:'var(--text-faint)'},
  bar:{flex:'1 1 auto',minWidth:24,height:1,margin:'0 2px'},
};

// --- Left rail stepper (alt) --------------------------------------------
function VStepper({ steps, active, setActive, completion }) {
  return (
    <aside style={vsStyle.root}>
      <div style={vsStyle.title}>Этапы запуска</div>
      <ol style={vsStyle.list}>
        {steps.map((s, i) => {
          const isActive = i === active;
          const state = isActive ? 'current' : completion[i];
          return (
            <li key={s.id}>
              <button onClick={()=>setActive(i)} style={{
                ...vsStyle.item,
                background: isActive ? 'var(--brand-soft)' : 'transparent',
                color: state === 'todo' ? 'var(--text-faint)' : 'var(--text)',
              }}>
                <span style={{
                  ...hsStyle.bullet,
                  ...(state==='done'?hsStyle.bulletDone:{}),
                  ...(state==='current'?hsStyle.bulletCurrent:{}),
                  ...(state==='warn'?hsStyle.bulletWarn:{}),
                }}>
                  {state==='done'?<Ic.check style={{color:'#fff'}}/>:
                   state==='warn'?<Ic.warn style={{color:'#fff'}}/>:
                   <span className="mono" style={{fontSize:11,fontWeight:600}}>{i+1}</span>}
                </span>
                <span style={{display:'flex',flexDirection:'column',lineHeight:1.2,textAlign:'left'}}>
                  <span style={{fontSize:13,fontWeight:500}}>{s.label}</span>
                  <span style={{fontSize:11,color:'var(--text-faint)'}}>{s.sub}</span>
                </span>
              </button>
            </li>
          );
        })}
      </ol>
    </aside>
  );
}
const vsStyle = {
  root:{width:240,minWidth:240,borderRight:'1px solid var(--line)',
    background:'var(--bg-panel)',padding:'16px 12px',display:'flex',flexDirection:'column',gap:10},
  title:{fontSize:11,fontWeight:600,letterSpacing:'.08em',textTransform:'uppercase',
    color:'var(--text-faint)',padding:'0 6px'},
  list:{listStyle:'none',margin:0,padding:0,display:'flex',flexDirection:'column',gap:2},
  item:{display:'flex',alignItems:'center',gap:10,width:'100%',padding:'8px 8px',
    border:0,borderRadius:6,cursor:'default'},
};

// --- Form atoms ----------------------------------------------------------
function Field({ label, hint, required, error, children, right }) {
  return (
    <label style={{display:'flex',flexDirection:'column',gap:4, minWidth:0}}>
      <span style={{display:'flex',alignItems:'center',justifyContent:'space-between',gap:8}}>
        <span style={{fontSize:12,color:'var(--text-muted)',fontWeight:500}}>
          {label}{required && <span style={{color:'var(--alert)'}}> *</span>}
        </span>
        {right}
      </span>
      {children}
      {hint && !error && <span style={{fontSize:11,color:'var(--text-faint)'}}>{hint}</span>}
      {error && <span style={{fontSize:11,color:'var(--alert)'}}>{error}</span>}
    </label>
  );
}

function Select({ value, onChange, options, placeholder, mono, disabled, invalid }) {
  return (
    <div style={{position:'relative'}}>
      <select
        value={value ?? ''}
        disabled={disabled}
        onChange={(e)=>onChange && onChange(e.target.value)}
        style={{
          appearance:'none', WebkitAppearance:'none',
          width:'100%', height:'var(--input-h)', padding:'0 28px 0 10px',
          background: disabled?'var(--bg-sunken)':'var(--bg-panel)',
          color:'var(--text)',
          border:`1px solid ${invalid?'var(--alert)':'var(--line-strong)'}`,
          borderRadius:'var(--radius)', fontFamily: mono?'var(--mono)':'var(--sans)',
          fontSize:'var(--fs)',
        }}>
        {placeholder && <option value="">{placeholder}</option>}
        {options.map(o => (
          <option key={o.value??o} value={o.value??o}>{o.label??o}</option>
        ))}
      </select>
      <span style={{position:'absolute',right:8,top:'50%',transform:'translateY(-50%)',color:'var(--text-muted)',pointerEvents:'none'}}>
        <Ic.chevDown/>
      </span>
    </div>
  );
}

function Input({ value, onChange, placeholder, mono, suffix, prefix, type="text", invalid, disabled, readOnly }){
  return (
    <div style={{
      display:'flex',alignItems:'center',
      height:'var(--input-h)', padding:'0 10px',
      background: disabled||readOnly?'var(--bg-sunken)':'var(--bg-panel)',
      border:`1px solid ${invalid?'var(--alert)':'var(--line-strong)'}`,
      borderRadius:'var(--radius)',
      fontFamily: mono?'var(--mono)':'var(--sans)',
    }}>
      {prefix && <span style={{color:'var(--text-faint)',marginRight:6}}>{prefix}</span>}
      <input type={type} value={value??''} placeholder={placeholder}
        onChange={(e)=>onChange && onChange(e.target.value)}
        disabled={disabled} readOnly={readOnly}
        style={{flex:1,minWidth:0,border:0,outline:'none',background:'transparent',
          color:'inherit',fontFamily:'inherit',fontSize:'var(--fs)',padding:0}}/>
      {suffix && <span style={{color:'var(--text-faint)',marginLeft:6}} className="mono">{suffix}</span>}
    </div>
  );
}

function Btn({ children, variant='secondary', size='md', onClick, disabled, icon, style }){
  const base = {
    display:'inline-flex',alignItems:'center',gap:6,
    height: size==='sm'?26:(size==='lg'?40:32),
    padding: size==='sm'?'0 10px':(size==='lg'?'0 18px':'0 12px'),
    fontSize: size==='sm'?12:(size==='lg'?14:13),
    fontWeight:500, borderRadius:6, border:'1px solid var(--line-strong)',
    background:'var(--bg-panel)', color:'var(--text)', cursor:'default',
    fontFamily:'inherit',
  };
  const styles = {
    primary:   { background:'var(--brand)', borderColor:'var(--brand)', color:'#fff'},
    growth:    { background:'var(--growth)', borderColor:'var(--growth)', color:'#fff'},
    secondary: base,
    ghost:     { ...base, background:'transparent', borderColor:'transparent', color:'var(--text-muted)'},
    danger:    { background:'var(--alert)', borderColor:'var(--alert)', color:'#fff'},
  };
  const v = variant==='secondary' ? base : { ...base, ...styles[variant] };
  return (
    <button onClick={onClick} disabled={disabled}
      style={{...v, opacity:disabled?0.5:1, ...style}}>
      {icon}
      {children}
    </button>
  );
}

function Chip({ tone='neutral', children, icon }){
  const toneMap = {
    neutral:{bg:'var(--bg-sunken)',fg:'var(--text-muted)',bd:'var(--line)'},
    brand:  {bg:'var(--brand-soft)',fg:'var(--brand-ink)',bd:'var(--brand-soft)'},
    growth: {bg:'var(--growth-soft)',fg:'var(--growth)',bd:'var(--growth-soft)'},
    warn:   {bg:'var(--warn-soft)',fg:'var(--warn)',bd:'var(--warn-soft)'},
    alert:  {bg:'var(--alert-soft)',fg:'var(--alert)',bd:'var(--alert-soft)'},
  };
  const t = toneMap[tone];
  return (
    <span style={{display:'inline-flex',alignItems:'center',gap:4,
      padding:'2px 8px',borderRadius:999,fontSize:11,fontWeight:500,
      background:t.bg,color:t.fg,border:`1px solid ${t.bd}`}}>
      {icon}{children}
    </span>
  );
}

function Card({ title, right, children, pad=true, style }){
  return (
    <section style={{background:'var(--bg-panel)',border:'1px solid var(--line)',
      borderRadius:8,overflow:'hidden',...style}}>
      {title && (
        <header style={{display:'flex',alignItems:'center',justifyContent:'space-between',
          padding:'10px 14px',borderBottom:'1px solid var(--line)',background:'var(--bg-panel)'}}>
          <div style={{fontSize:13,fontWeight:600}}>{title}</div>
          <div style={{display:'flex',gap:6,alignItems:'center'}}>{right}</div>
        </header>
      )}
      <div style={{padding: pad ? 14 : 0}}>{children}</div>
    </section>
  );
}

function Hint({ children, show }){
  if (!show) return null;
  return (
    <div style={{display:'flex',gap:8,padding:'10px 12px',
      border:'1px dashed var(--line-strong)',borderRadius:6,
      background:'var(--bg-sunken)',color:'var(--text-muted)',fontSize:12}}>
      <Ic.info style={{color:'var(--brand)',flex:'0 0 auto',marginTop:1}}/>
      <div>{children}</div>
    </div>
  );
}

function Tabs({ tabs, active, onChange }){
  return (
    <div style={{display:'flex',borderBottom:'1px solid var(--line)',gap:4,padding:'0 2px'}}>
      {tabs.map(t => (
        <button key={t.id} onClick={()=>onChange(t.id)} style={{
          padding:'8px 12px',border:0,background:'transparent',
          color: active===t.id?'var(--text)':'var(--text-muted)',
          borderBottom: active===t.id?'2px solid var(--brand)':'2px solid transparent',
          fontWeight:500,fontSize:13,cursor:'default',marginBottom:-1,
          display:'inline-flex',alignItems:'center',gap:6
        }}>{t.icon}{t.label}{t.count!=null && <span className="mono" style={{fontSize:11,color:'var(--text-faint)'}}>{t.count}</span>}</button>
      ))}
    </div>
  );
}

// --- Placeholder strips for images --------------------------------------
function StripePlaceholder({ w=120, h=80, label }){
  return (
    <div style={{width:w,height:h,
      background:'repeating-linear-gradient(135deg,var(--bg-sunken) 0 6px,var(--bg-panel) 6px 12px)',
      border:'1px dashed var(--line-strong)',borderRadius:6,
      display:'flex',alignItems:'center',justifyContent:'center',
      color:'var(--text-faint)',fontFamily:'var(--mono)',fontSize:10}}>
      {label}
    </div>
  );
}

Object.assign(window, { TopBar, HStepper, VStepper, Field, Select, Input, Btn, Chip, Card, Hint, Tabs, StripePlaceholder });
