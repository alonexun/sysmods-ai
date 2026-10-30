import React, { useEffect, useRef, useState } from 'react'
import { api, getJSON, getToken, setToken, money, fmt, pct } from '../api'
import { Badge, DataTable } from '../ui'

const CN = {
  'pv.capacity_kw': '光伏装机', 'wind.capacity_kw': '风电装机',
  'pemwe.rated_kw': 'PEM 电解功率', 'alk.rated_kw': 'ALK 电解功率',
  'aem.rated_kw': 'AEM 电解功率', 'soec.rated_kw': 'SOEC 电解功率',
  'bess.capacity_kwh': '锂电池容量', 'h2store.capacity_kg': '储氢容量',
  'chem.nh3.capacity_t_per_h': '合成氨额定产量', 'fc.rated_kw': '燃料电池功率',
  'load.avg_kw': '平均负荷', 'grid.max_import_kw': '购电红线',
}
const EXAMPLES = [
  '在内蒙古建设风光绿氨项目：风电 1500kW、光伏 800kW，PEM 700kW，储氢 5000kg，合成氨每小时 0.8 吨，目标全年高负荷稳定产氨。',
  '高原边防哨站离网供电：光伏 50kW、锂电 200kWh、PEM 25kW、储氢 500kg，保供率要求 99.9%。',
]
const WELCOME = `<h4>从一个工程目标开始</h4>
用自然语言描述地点、设备规模、产品目标和保供要求。平台会把对话整理为可核对的参数卡，再进入仿真、优化与报告签收。<br><br>
<b>推荐流程</b><br>描述项目 → 确认参数 → 运行仿真 → 容量优化 → 审阅并签收报告。<br><br>
<span class="small">可先点击下方示例填入输入框；首次发送任意消息将自动完成测试注册。所有物理数值均由服务端确定性内核计算。</span>`

export default function ChatApp() {
  const [phone, setPhone] = useState('13800000001')
  const [credits, setCredits] = useState(null)
  const [registered, setRegistered] = useState(!!getToken())
  const [sid, setSid] = useState(null)
  const [paramCard, setParamCard] = useState(null)
  const [result, setResult] = useState(null)
  const [state, setState] = useState('未开始')
  const [messages, setMessages] = useState([{ html: WELCOME, cls: 'bot' }])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [tab, setTab] = useState('params')
  const chatEnd = useRef(null)

  const addMsg = (html, cls = 'bot') =>
    setMessages(prev => [...prev, { html, cls }])
  const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
  const runSafe = async fn => {
    try { await fn() } catch (e) {
      addMsg(`<div class="errorBox"><b>操作未完成</b><br>${esc(e.message || e)}。请检查输入、积分或服务状态后重试。</div>`)
    }
  }

  const refreshCredits = async () => {
    try {
      const j = await getJSON('/ledger/' + phone)
      if (j.balance !== undefined) setCredits(j.balance)
    } catch { /* 未注册 */ }
  }
  useEffect(() => { if (registered) refreshCredits() }, [registered, phone])
  useEffect(() => { chatEnd.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages])

  const actions = [
    !sid && { label: '填入绿氨示例', fn: () => setInput(EXAMPLES[0]) },
    !sid && { label: '填入离网站点示例', fn: () => setInput(EXAMPLES[1]) },
    sid && state === 'G1 参数卡待确认' && { label: '确认参数卡（G1）', primary: true, fn: doG1 },
    sid && state === 'G1 已确认' && { label: '运行仿真', primary: true, fn: doRun },
    sid && state === 'G4 审阅中' && { label: '容量优化', fn: doOptimize },
    sid && state === 'G4 审阅中' && { label: '签收并查看报告', primary: true, fn: doG5 },
    sid && paramCard && state !== 'G5 已签收' && { label: '查看系统架构', fn: () => setTab('diagram') },
    sid && state === 'G5 已签收' && { label: '查看已签收报告', primary: true,
      fn: () => { window.location.hash = `/report/${sid}` } },
  ].filter(Boolean)

  async function doG1() {
    const j = await api(`/session/${sid}/g1`, { phone, overrides: {} })
    addMsg(`✅ <b>G1 参数卡已确认</b>（版本 V${j.version}）。点击「运行仿真」继续。`)
    setState('G1 已确认')
  }
  async function doRun() {
    setBusy(true)
    addMsg('⏳ 仿真运行中（确定性内核 · 逐时守恒审计）…')
    try {
      const j = await api(`/session/${sid}/run`, { phone })
      if (j.state === 'G4_PENDING') {
        const r = j.result; setResult(r); setState('G4 审阅中')
        const k = r.kpi, e = r.econ, isT6 = k.nh3_annual_t !== undefined
        const cards = isT6
          ? [['净 NPC', money(e.npc_net_cny)], ['LCOA', money(e.lcoa_cny_per_t) + '/t'], ['绿氨产量', fmt(k.nh3_annual_t) + ' t']]
          : [['保供率', pct(k.reliability)], ['LCOE', money(e.lcoe_cny_per_kwh) + '/kWh'], ['年制氢', fmt(k.h2_prod_kg) + ' kg']]
        addMsg(`📊 <b>仿真完成</b> <span class="badge b-${r.cons_passed ? 'pass' : 'fail'}">守恒 ${r.cons_passed ? 'PASS' : 'FAIL'}</span>` +
          `<span class="badge b-${r.confidence.grade.toLowerCase()}">置信度 ${r.confidence.grade}</span>` +
          `<div class="kpiRow">${cards.map(c => `<div class="kpiBox"><b>${c[1]}</b><span>${c[0]}</span></div>`).join('')}</div>` +
          `<div class="small">${esc(r.confidence.attribution)}</div>` +
          `<div class="small">审阅后可「容量优化」或输入变更（如"把光伏改到 800 千瓦"），满意后「签收并查看报告」。</div>`)
        setTab('result'); refreshCredits()
      } else {
        addMsg(`⚠️ <b>G3 异常处置</b>：${(j.g3 || []).join(' / ')}<div class="small">${esc(j.cons_summary || '')}</div>`)
        setState('G3 异常')
      }
    } finally { setBusy(false) }
  }
  async function doOptimize() {
    const p = paramCard.params || {}
    const isT6 = (paramCard.template || '').startsWith('T6')
    const cands = isT6
      ? { 'pemwe.rated_kw': [Math.max(50, p['pemwe.rated_kw'] * 0.5), p['pemwe.rated_kw'], p['pemwe.rated_kw'] * 1.5],
          'h2store.capacity_kg': [p['h2store.capacity_kg'] * 0.5, p['h2store.capacity_kg'], p['h2store.capacity_kg'] * 2] }
      : { 'pv.capacity_kw': [Math.max(5, p['pv.capacity_kw'] * 0.5), p['pv.capacity_kw'], p['pv.capacity_kw'] * 2],
          'bess.capacity_kwh': [p['bess.capacity_kwh'] * 0.5, p['bess.capacity_kwh'], p['bess.capacity_kwh'] * 2] }
    setBusy(true)
    addMsg(`⏳ 容量优化：穷举 ${Object.values(cands).reduce((a, b) => a * b.length, 1)} 组合 + NPC 排序…`)
    try {
      const j = await api(`/session/${sid}/optimize`, { phone, candidates: cands, n_days: 30, refine_days: 60 })
      const keys = Object.keys(cands)
      const rows = j.top.map(r => ({
        cells: ['#' + r.rank, money(r.npc_cny), keys.map(k => fmt(r[k], 0)).join(' / '), pct(r.reliability)],
        _cls: r.rank === 1 ? 'best' : ''
      }))
      addMsg(`🏆 <b>优化结果</b>（${j.n_combinations} 组合 · 可行 ${j.n_feasible} · ${j.elapsed_s}s）` +
        `<table class="data"><thead><tr><th>#</th><th>净 NPC</th><th>容量组合</th><th>保供</th></tr></thead><tbody>` +
        rows.map(r => `<tr class="${r._cls}">${r.cells.map(c => `<td>${c}</td>`).join('')}</tr>`).join('') +
        `</tbody></table><div class="small">首行为最优。签收报告会单列优化推荐方案设备卡；采纳后请通过变更单重算。</div>`)
      refreshCredits()
    } finally { setBusy(false) }
  }
  async function doG5() {
    const j = await api(`/session/${sid}/g5`, { phone })
    addMsg('🖊️ <b>已签收，版本锁定。</b>')
    addMsg(`<a class="reportLink" href="#/report/${sid}"><b>→ 打开交互式报告（React · 目录/需求回顾/参数中英文）</b></a>` +
      `　<a href="${j.report_url}" target="_blank">下载自包含 HTML</a>`)
    setState('G5 已签收'); refreshCredits()
  }
  async function doConfirmChange() {
    const c = await api(`/session/${sid}/change/confirm`, { phone, text: '确认变更' })
    addMsg(`✅ 变更已执行并重算（第 ${c.rounds} 轮）。`)
    setResult(c.result); refreshCredits()
  }

  async function sendInternal() {
    const text = input.trim(); if (!text || busy) return
    setInput(''); addMsg(esc(text), 'user')
    if (!registered) {
      const j = await api('/auth/register', { phone })
      setRegistered(true); setToken(j.token)
      addMsg(`✅ <b>注册成功</b>，余额 ${j.credits} 积分（月度免费 50）。请描述项目，例如：<i>在内蒙古建风光绿氨项目，合成氨每小时 1 吨。</i>`)
      refreshCredits(); return
    }
    if (!sid) {
      const j = await api('/session', { phone, description: text })
      setSid(j.sid); setParamCard(j.param_card); setState('G1 参数卡待确认')
      const c = j.param_card
      addMsg(`📋 <h4>场景识别：${esc(c.scenario)}（模板 ${esc(c.template)}）</h4>` +
        `参数完整度 <b>${Math.round(c.completeness * 100)}%</b>——右侧「参数卡」可查看与修改。` +
        `<ol>${c.questions.map(q => `<li>${esc(q)}</li>`).join('')}</ol>` +
        `<div class="small">点击「确认参数卡（G1）」锁定需求；也可先在对话中修改。</div>`)
      addMsg('🧩 <b>模型盲区</b>（仿真边界外，需人工确认）：' +
        j.gap_cards.slice(0, 4).map(g => `<div class="gapcard"><b>${esc(g.topic)}</b>：${esc(g.impact)}</div>`).join(''))
      setTab('params'); return
    }
    if (text.includes('确认变更')) return doConfirmChange()
    if (text === '确认' || text.includes('G1')) return doG1()
    if (text.includes('运行') || text.includes('仿真')) return doRun()
    if (text.includes('优化')) return doOptimize()
    if (text.includes('签收') || text.includes('G5')) return doG5()
    const j = await api(`/session/${sid}/change`, { phone, text })
    if (j.need_clarification) {
      addMsg(`🤔 ${esc(j.msg)}<div class="small">可继续：运行仿真 / 容量优化 / 签收 / 明确变更（如"把光伏改到 80 千瓦"）。</div>`)
      return
    }
    addMsg(`📋 <b>变更单回显</b>：${esc(j.echo)}<div class="small">点击「确认变更」执行。</div>`)
  }

  /* ---------------- 工作面板 ---------------- */
  const panelBody = () => {
    if (tab === 'params') {
      if (!paramCard) return <div className="empty"><b>等待项目描述</b>系统会在这里生成可核对的设备参数卡。<ol><li>识别场景与模板</li><li>标注参数等级与完整度</li><li>确认后进入仿真</li></ol></div>
      const rows = Object.keys(CN).filter(kk => paramCard.params?.[kk] !== undefined).map(kk => ({
        cells: [CN[kk], fmt(paramCard.params[kk], 2),
        <span className={`lv ${(paramCard.levels?.[kk] || 'C')[0]}`}>{paramCard.levels?.[kk] || ''}</span>]
      }))
      return (<div className="card">
        <h3>{paramCard.scenario} · {paramCard.template}</h3>
        <div className="small">参数完整度 {Math.round((paramCard.completeness || 0) * 100)}%</div>
        <div className="progress"><div style={{ width: `${(paramCard.completeness || 0) * 100}%` }} /></div>
        <DataTable head={['参数', '值', '等级']} numCols={[1]} rows={rows} />
      </div>)
    }
    if (tab === 'result') {
      if (!result) return <div className="empty"><b>尚无仿真结果</b>完成参数确认并运行后，这里会显示核心 KPI、经济性与保供情况。</div>
      const entries = Object.entries(result.kpi || {}).filter(([, v]) => typeof v === 'number').slice(0, 16)
        .map(([kk, v]) => ({ cells: [kk, fmt(v, 2)] }))
      const econs = Object.entries(result.econ || {}).filter(([, v]) => typeof v === 'number').slice(0, 10)
        .map(([kk, v]) => ({ cells: [kk, kk.includes('cny') ? money(v) : fmt(v, 2)] }))
      return (<>
        <div className="card"><h3>核心 KPI</h3><DataTable head={['指标', '值']} numCols={[1]} rows={entries} /></div>
        <div className="card"><h3>经济性</h3><DataTable head={['指标', '值']} numCols={[1]} rows={econs} /></div>
      </>)
    }
    if (tab === 'diagram') {
      if (!sid) return <div className="empty"><b>系统架构预览</b>创建会话后，按设备参数自动生成总线与设备连接图。</div>
      return <DiagramBox sid={sid} />
    }
  }
  return (
    <div className="workRoot">
      <header className="workHead">
        <div className="brand">
          <img className="logoImg" src="/logo.png" alt="Sysmods AI" />
          <div className="sub">分布式氢能方案工作台 · 确定性物理内核</div></div>
        <div className="hright">
          <span className="modelTag">交互: DeepSeek（无 key 时规则模式）｜数值: 服务端内核</span>
          <input value={phone} onChange={e => setPhone(e.target.value)} className="phoneIn" />
          <span className="credits">{credits != null ? `积分 ${credits}` : '未注册'}</span>
        </div>
      </header>
      <main className="workMain">
        <section className="chatCol">
          <div className="chatHead"><b>方案对话</b><span className="state">{state}</span></div>
          <div className="chatScroll">
            {messages.map((mm, i) => <div key={i} className={`msg ${mm.cls}`} dangerouslySetInnerHTML={{ __html: mm.html }} />)}
            <div ref={chatEnd} />
          </div>
          <div className="actionBar">
            <div className="btnRow">
              {actions.map((a, i) => <button key={i} disabled={a.disabled || busy}
                className={a.primary ? 'primary' : ''} onClick={() => runSafe(a.fn)}>{a.label}</button>)}
              {state === 'G4 审阅中' && <button disabled={busy} onClick={() => runSafe(doConfirmChange)}>确认变更</button>}
            </div>
            <div className="inputRow">
              <input value={input} onChange={e => setInput(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && runSafe(sendInternal)}
                placeholder="描述项目，或输入变更（如：把光伏改到 800 千瓦）" />
              <button className="primary" disabled={busy} onClick={() => runSafe(sendInternal)}>发送</button>
            </div>
            <div className="hint">注册 → 描述项目 → 确认参数卡 → 运行 → 审阅/变更/优化 → 签收看报告。支持文字命令：确认 / 运行 / 确认变更 / 优化 / 签收。</div>
          </div>
        </section>
        <aside className="panelCol">
          <div className="ptabs">
            {[['params', '参数卡'], ['result', '结果'], ['diagram', '系统架构']].map(([t, l]) =>
              <button key={t} className={tab === t ? 'active' : ''} onClick={() => setTab(t)}>{l}</button>)}
          </div>
          <div className="panelBody">{panelBody()}</div>
        </aside>
      </main>
    </div>
  )
}

function DiagramBox({ sid }) {
  const [svg, setSvg] = useState('加载中…')
  useEffect(() => {
    fetch(`/session/${sid}/diagram`).then(r => r.text()).then(setSvg).catch(() => setSvg('加载失败'))
  }, [sid])
  return (<div className="card">
    <h3>系统架构示意图</h3>
    <div className="diagramBox" dangerouslySetInnerHTML={{ __html: svg }} />
    <div className="hint">按当前参数卡动态生成：电=蓝 / 氢=绿 / 热=橙 / 物料=灰。</div>
  </div>)
}
