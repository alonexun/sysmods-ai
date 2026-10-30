import React, { useEffect, useState } from 'react'
import ChatApp from './chat/ChatApp'
import ReportView from './report/ReportView'

const currentHash = () => window.location.hash || '#/'

/* Hash 路由：#/ → 工作台；#/report/{sid} → React 交互式报告 */
export default function App() {
  const [hash, setHash] = useState(currentHash)
  useEffect(() => {
    const onChange = () => setHash(currentHash())
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])
  const m = hash.match(/^#\/report\/(\S+)/)
  return m ? <ReportView sid={m[1]} /> : <ChatApp />
}
