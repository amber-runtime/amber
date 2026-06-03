import { useEffect } from 'react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { AuthGate } from './lib/auth'
import { WorkflowProvider } from './lib/workflowContext'
import { fetchPricing } from './lib/api'
import { setPricing } from './lib/pricingStore'
import { WorkflowListPage } from './pages/list/WorkflowListPage'
import { WorkflowDetailPage } from './pages/details/WorkflowDetailPage'
import { ToastStack } from './shared/Toast'

const CONFIGURED_BASE = (import.meta.env.VITE_BASE_PATH as string | undefined) ?? import.meta.env.BASE_URL
const ROUTER_BASENAME = (CONFIGURED_BASE && CONFIGURED_BASE !== '/' ? CONFIGURED_BASE : '/admin/').replace(
  /\/$/,
  '',
)

export default function App() {
  return (
    <AuthGate>
      <DashboardApp />
    </AuthGate>
  )
}

function DashboardApp() {
  useEffect(() => {
    fetchPricing()
      .then((r) => setPricing(r.models, r.synced_at))
      .catch((e) => console.warn('Failed to fetch pricing:', e))
  }, [])

  return (
    <WorkflowProvider>
      <BrowserRouter basename={ROUTER_BASENAME}>
        <Routes>
          <Route path="/" element={<WorkflowListPage />} />
          <Route path="/workflows/:id" element={<WorkflowDetailPage />} />
        </Routes>
      </BrowserRouter>
      <ToastStack />
    </WorkflowProvider>
  )
}
