import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { WorkflowProvider } from './lib/workflowContext'
import { WorkflowListPage } from './pages/WorkflowListPage'
import { WorkflowDetailPage } from './pages/WorkflowDetailPage'
import { ToastStack } from './components/Toast'

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
