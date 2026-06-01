import { useEffect } from 'react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { WorkflowProvider } from './lib/workflowContext'
import { fetchPricing } from './lib/api'
import { setPricing } from './lib/pricingStore'
import { WorkflowListPage } from './pages/list/WorkflowListPage'
import { WorkflowDetailPage } from './pages/details/WorkflowDetailPage'
import { ToastStack } from './shared/Toast'

export default function App() {
  useEffect(() => {
    fetchPricing()
      .then((r) => setPricing(r.models, r.synced_at))
      .catch((e) => console.warn('Failed to fetch pricing:', e))
  }, [])

  return (
    <WorkflowProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<WorkflowListPage />} />
          <Route path="/workflows/:id" element={<WorkflowDetailPage />} />
        </Routes>
      </BrowserRouter>
      <ToastStack />
    </WorkflowProvider>
  )
}
