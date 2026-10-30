import React, { useEffect, useState } from 'react'
import { getJSON, money, fmt, pct } from '../api'
import { Badge, KpiCard, DataTable } from '../ui'

/* 设备卡：同一设备注册表，同时服务需求回顾与最终方案 */
const DeviceCards = ({ devices }) => (
  <div className="devgrid">
    {(devices || []).map(d => (
      <div className="devc" key={d.key} data-tone={d.tone || 'grid'}>
        <div className="t">
          <div className="deviceTitle">
            <span className="deviceIcon">{d.icon}</span>
            <div><b>{d.cn}</b><span>{d.en}</span></div>
          </div>
        </div>
        <div className="r">{d.rated}</div>
        {(d.specs || []).map((s, i) => (
          <div className="s" key={i}><span>{s.name}</span><span className="mono">{s.value}</span></div>
        ))}
      </div>
    ))}
  </div>
)

const SERIES_META = {
  pv_kw: ['光伏出力 PV kW', '#B7791F'],
  wind_kw: ['风电出力 Wind kW', '#2B6CB0'],
  pem_kw: ['电解总功率 Electrolysis kW', '#0E7C86'],
  h2_store_level_kg: ['储氢罐位 H2 Storage kg', '#7257A8'],
  nh3_t_per_h: ['合成氨产量 NH3 t/h', '#A7513C'],
  bess_soc: ['电池 SOC', '#52606D'],
}

/* 轻量 SVG 时序折线：离线可用，无 plotly 依赖 */
export const TimeSeriesChart = ({ data, label, color = '#2B6CB0', height = 160 }) => {
  const vals = data.map(x => Number(x) || 0)
  if (!vals.length) return null
  const W = 900, H = height, pad = { l: 48, r: 12, t: 10, b: 20 }
  const vmax = Math.max(...vals), vmin = Math.min(...vals)
  const span = (vmax - vmin) || 1
  const px = i => pad.l + (i / (vals.length - 1)) * (W - pad.l - pad.r)
  const py = v => H - pad.b - ((v - vmin) / span) * (H - pad.t - pad.b)
  const path = vals.map((v, i) => `${i === 0 ? 'M' : 'L'}${px(i).toFixed(1)},${py(v).toFixed(1)}`).join('')
  return (
    <div className="chart">
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label={label}>
        {[0, 0.5, 1].map(f => (
          <g key={f}>
            <line x1={pad.l} x2={W - pad.r} y1={py(vmin + f * span)} y2={py(vmin + f * span)}
              stroke="#DDE4DE" strokeDasharray="3,3" />
            <text x={pad.l - 6} y={py(vmin + f * span) + 3} textAnchor="end"
              fontSize="9" fill="#68746E">{fmt(vmin + f * span, span > 100 ? 0 : 1)}</text>
          </g>
        ))}
        <path d={path} fill="none" stroke={color} strokeWidth="1.5" />
      </svg>
      <div className="cap">{label}（{vals.length}h · 最大 {fmt(vmax)} · 最小 {fmt(vmin)}）</div>
    </div>
  )
}

const TOC = [
  ['recall', '1 需求回顾 Recall'],
  ['arch', '2 最终方案 Final Scheme'],
  ['kpi', '3 KPI 摘要 Summary'],
  ['detail', '4 发电/制氢明细 Production'],
  ['econ', '5 经济性 Economics'],
  ['opt', '6 容量优化 Optimization'],
  ['series', '7 逐时序列 Timeseries'],
  ['params', '8 参数清单 Parameters'],
  ['changes', '9 变更历史 Changes'],
  ['gaps', '10 盲区与声明 Notes'],
]

const Section = ({ id, num, cn, en, children }) => (
  <section id={id} className="sec">
    <h2><span className="num mono">{num}</span>{cn}<span className="en">{en}</span></h2>
    {children}
  </section>
)

export default function ReportView({ sid }) {
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')
  const [active, setActive] = useState('recall')

  useEffect(() => {
    setData(null); setErr('')
    getJSON(`/session/${sid}/report_data`).then(setData).catch(e => setErr(String(e.message || e)))
  }, [sid])

  useEffect(() => {
    if (!data) return undefined
    const onScroll = () => {
      let current = TOC[0][0]
      TOC.forEach(([id]) => {
        const el = document.getElementById(id)
        if (el && el.getBoundingClientRect().top <= 150) current = id
      })
      setActive(current)
    }
    window.addEventListener('scroll', onScroll, { passive: true })
    onScroll()
    return () => window.removeEventListener('scroll', onScroll)
  }, [data])

  if (err) return (
    <div className="pageState"><div className="card">
      <h3>无法加载报告</h3><p className="small">{err}</p><a href="#/">返回工作台</a>
    </div></div>
  )
  if (!data) return <div className="pageState"><div className="card">报告数据加载中…</div></div>

  const m = data.meta, rc = data.recall, k = data.kpi_table
  const plan = data.final_plan || {
    label: '签收方案', source: 'signed', devices: data.devices || [],
    diagram_svg: data.diagram_svg, changed: [], metrics: {}, note: '',
  }
  const grouped = {}
  ;(data.params || []).forEach(p => { (grouped[p.category || '其他'] ||= []).push(p) })
  const tsEntries = Object.entries(data.timeseries || {}).filter(([, v]) => v && v.length)

  return (
    <div className="repRoot">
      <header className="repHead no-print">
        <div className="brand">
          {data.logo_uri && <img className="logoImg" src={data.logo_uri} alt="Sysmods AI" />}
          <div className="sub mono">{m.session_id} · V{m.version} · {m.generated_at}</div>
        </div>
        <div className="headActions">
          <Badge cls={m.cons_passed ? 'pass' : 'fail'}>守恒 {m.cons_passed ? 'PASS' : 'FAIL'}</Badge>
          <Badge cls={m.confidence.grade.toLowerCase()}>置信度 {m.confidence.grade}</Badge>
          <a href="#/">返回工作台</a>
          <button onClick={() => window.print()}>打印 / 存 PDF</button>
          <a className="dl" href={`/report/${sid}`} target="_blank" rel="noreferrer">下载 HTML</a>
        </div>
      </header>

      <div className="repLayout">
        <nav className="tocSide no-print" aria-label="报告目录">
          <div className="tocTitle">报告目录</div>
          {TOC.map(([id, label]) => (
            <a key={id} href={`#${id}`} className={active === id ? 'active' : ''}
              onClick={() => setActive(id)}>{label}</a>
          ))}
        </nav>

        <main className="repBody">
          {!m.cons_passed && <div className="failbox">守恒审计未通过——本报告结果不可用（G3 异常处置未完成）。</div>}

          <section className="reportHero">
            <div>
              <div className="heroEyebrow">ENGINEERING REPORT · V{m.version}</div>
              <h1>分布式氢能方案计算报告</h1>
              <p>{rc.scenario} · {rc.template} · {plan.label}</p>
              <div className="heroMeta">
                <span>会话 {m.session_id}</span><span>{m.generated_at}</span>
                <span>守恒 {m.cons_passed ? 'PASS' : 'FAIL'}</span>
              </div>
            </div>
            <div className="heroSide">
              <div className="heroGrade">{m.confidence.grade}</div>
              <small>置信度等级<br />{m.confidence.attribution}</small>
            </div>
          </section>

          <Section id="recall" num="1." cn="需求回顾" en="Requirements Recall">
            <div className="card goal">
              <h3>您提供的项目目标</h3>
              <p className="goalText">{rc.goal}</p>
              <div className="metaRow mono">
                场景 {rc.scenario} · 模板 {rc.template} · 参数完整度 {Math.round((rc.completeness || 0) * 100)}%
              </div>
            </div>
            <div className="card">
              <h3>当前输入设备（需求参数）</h3>
              <DeviceCards devices={data.devices} />
              {rc.priori_count > 0 && <p className="small">
                其余 {rc.priori_count} 项采用平台先验/注册表默认值（含 C 级，§8 标注等级与出处）。
              </p>}
            </div>
            <div className="card">
              <h3>方案目标与约束</h3>
              <p>{rc.objective}</p>
              {rc.changes.length > 0 && (<>
                <h3>您在会话中的变更</h3>
                <ul>{rc.changes.map((c, i) => <li key={i}>{c.echo}（{c.confirmed ? '已确认' : '未确认'}）</li>)}</ul>
              </>)}
              {rc.unconfirmed_questions.length > 0 && (<>
                <h3>尚未回答的问题（按先验处理）</h3>
                <ul className="qs">{rc.unconfirmed_questions.map((q, i) => <li key={i}>{q}</li>)}</ul>
              </>)}
              <p className="recallNote">{rc.note}</p>
            </div>
          </Section>

          <Section id="arch" num="2." cn="最终方案与系统架构" en="Final Scheme & Architecture">
            <div className="planHead">
              <span className="planLabel">{plan.label}</span>
              <div className="planMetrics">
                {plan.source === 'optimization' ? (<>
                  复核净 NPC <b>{money(plan.metrics.npc_cny)}</b><br />
                  保供率 <b>{pct(plan.metrics.reliability)}</b>
                  {plan.metrics.note && <div className="small">{plan.metrics.note}</div>}
                </>) : '当前签收工况'}
              </div>
            </div>
            {plan.changed.length > 0 && (
              <div className="changeChips">
                {plan.changed.map(c => (
                  <span className="changeChip" key={c.canonical}>
                    {c.cn}: {fmt(c.from, 2)} → <b>{fmt(c.to, 2)}</b>
                  </span>
                ))}
              </div>
            )}
            <DeviceCards devices={plan.devices} />
            <div className="planNote">{plan.note}</div>
            <div className="card fig" dangerouslySetInnerHTML={{ __html: plan.diagram_svg }} />
            <p className="small">图例：电=蓝 · 氢=绿 · 热=橙 · 物料=灰。设备卡与架构图均按最终方案参数生成。</p>
          </Section>

          <Section id="kpi" num="3." cn="KPI 摘要" en="Key Indicators">
            <div className="kpis">{(data.kpi_cards || []).map((c, i) =>
              <KpiCard key={i} label={c.label} value={c.value} unit={c.unit} sub={c.sub} />)}</div>
            {plan.source === 'optimization' && <p className="small">以下为签收工况 KPI；优化推荐候选的复核 NPC 与保供率见 §2。</p>}
            <DataTable head={['指标 Indicator', '值 Value']}
              numCols={[1]}
              rows={Object.entries(k).map(([kk, v]) => ({ cells: [kk, typeof v === 'number' ? fmt(v, 2) : String(v)] }))} />
          </Section>

          <Section id="detail" num="4." cn="发电 / 制氢明细" en="Production Details">
            <DataTable head={['项目 Item', '数量 Quantity', '单位 Unit', '备注 Note']}
              numCols={[1]}
              rows={(data.generation_detail || []).map(g => ({ cells: [g.name, g.value, g.unit, g.note] }))} />
          </Section>

          <Section id="econ" num="5." cn="经济性" en="Economics">
            <DataTable head={['指标', '值']} numCols={[1]}
              rows={(data.economics?.rows || []).map(r => ({ cells: [r.name, r.value] }))} />
            <h3>成本明细 Cost Breakdown（组件 × 投资 / 寿命 / 年运维）</h3>
            <DataTable head={['组件 Component', '初始投资 CAPEX', '寿命 Life', '年运维 OPEX']}
              numCols={[1, 2, 3]}
              rows={(data.economics?.cost_items || []).map(it => ({
                cells: [it.label, money(it.capex), it.life_years + ' 年', money(it.opex_annual)]
              }))} />
            <p className="small">{data.economics?.note}</p>
          </Section>

          <Section id="opt" num="6." cn="容量配置优化" en="Optimization">
            {data.optimization?.length ? (
              <DataTable
                head={Object.keys(data.optimization[0])}
                numCols={Object.keys(data.optimization[0]).map((c, i) =>
                  i === 0 ? 0 : (typeof data.optimization[0][c] === 'number' ? i : -1)).filter(i => i >= 0)}
                rows={data.optimization.map((r, i) => ({
                  _cls: i === 0 ? 'best' : '',
                  cells: Object.values(r).map(v => typeof v === 'number'
                    ? (Math.abs(v) > 100 ? v.toLocaleString('zh-CN', { maximumFractionDigits: 0 }) : fmt(v, 3))
                    : v)
                }))} />
            ) : <p className="small">未执行容量优化。</p>}
            <p className="small">穷举 + 可行性过滤 + Total NPC 升序（HOMER 口径）；首行最优（高亮）。</p>
          </Section>

          <Section id="series" num="7." cn="逐时序列" en="Timeseries">
            {tsEntries.length ? tsEntries.map(([key, v]) => {
              const [label, color] = SERIES_META[key] || [key, '#2B6CB0']
              return <TimeSeriesChart key={key} data={v} label={label} color={color} />
            }) : <p className="small">本报告未嵌入逐时序列。</p>}
          </Section>

          <Section id="params" num="8." cn="参数清单" en="Parameters (中英对照)">
            {Object.entries(grouped).map(([cat, items], idx) => (
              <details key={cat} className="paramGroup" open={idx === 0}>
                <summary>{cat} · {items.length} 项</summary>
                <DataTable head={['中文参数', 'canonical', '值', '单位', '等级']}
                  numCols={[2]}
                  rows={items.map(p => ({
                    cells: [p.cn, p.canonical, fmt(p.value, 3), p.unit,
                      <span className={`lv ${(p.level || 'C')[0]}`}>{p.level}</span>]
                  }))} />
              </details>
            ))}
          </Section>

          <Section id="changes" num="9." cn="变更历史" en="Change History">
            {data.orders?.length ? (
              <DataTable head={['#', '变更单', '状态']}
                rows={data.orders.map((o, i) => ({ cells: [i + 1, o.echo, o.confirmed ? '已确认' : '待确认'] }))} />
            ) : <p className="small">无变更记录。</p>}
          </Section>

          <Section id="gaps" num="10." cn="模型盲区与声明" en="Notes & Disclaimer">
            <div className="notebox">以下因素在仿真边界外——数值须人工确认后回填（转 C 级先验）。</div>
            <DataTable head={['主题', '模型覆盖', '影响', '建议']}
              rows={(data.gaps || []).map(g => ({ cells: [g.topic, g.covered_by_model, g.impact, g.advice] }))} />
            {data.unresolved?.length > 0 && (<>
              <h3>未决问题</h3>
              <ul>{data.unresolved.map((q, i) => <li key={i}>{q}</li>)}</ul>
            </>)}
            <div className="disclaimer">
              <b>声明：</b>交互语言与流程编排由 {m.llm_model} 驱动；全部物理数值由 Sysmods AI
              服务端确定性内核计算产生（LLM 不产生任何计算结果）。守恒审计：电/氢平衡年误差门限 0.5%，
              本报告结论{m.cons_passed ? '通过' : '未通过'}。结果供投资决策参考，详细设计须注册工程师复核。
            </div>
            <p className="small mono">KB 版本：{Object.entries(data.kb_manifest || {}).map(([a, v]) => `${a}:${v.version}`).join(' · ')}</p>
          </Section>
        </main>
      </div>
    </div>
  )
}
