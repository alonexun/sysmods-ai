import React from 'react'

export const Badge = ({ cls, children }) =>
  <span className={`badge b-${cls}`}>{children}</span>

export const KpiCard = ({ label, value, unit, sub }) => (
  <div className="kpi">
    <div className="v">{value}<span className="u">{unit}</span></div>
    <div className="l">{label}</div>
    {sub && <div className="s">{sub}</div>}
  </div>
)

export const DataTable = ({ head, rows, numCols = [] }) => (
  <div className="tableWrap">
    <table className="data">
      <thead><tr>{head.map((h, i) => <th key={i} className={numCols.includes(i) ? 'num' : ''}>{h}</th>)}</tr></thead>
      <tbody>
        {rows.map((r, i) => <tr key={i} className={r._cls || ''}>
          {r.cells.map((c, j) => <td key={j} className={numCols.includes(j) ? 'num' : ''}>{c}</td>)}
        </tr>)}
      </tbody>
    </table>
  </div>
)
