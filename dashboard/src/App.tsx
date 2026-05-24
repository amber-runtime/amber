import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { WorkflowProvider } from './lib/workflowContext'
import { WorkflowListPage } from './pages/list/WorkflowListPage'
import { WorkflowDetailPage } from './pages/details/WorkflowDetailPage'
import { ToastStack } from './shared/Toast'

export default function App() {
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
