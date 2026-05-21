import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { WorkflowListPage } from './pages/WorkflowListPage'
import { WorkflowDetailPage } from './pages/WorkflowDetailPage'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<WorkflowListPage />} />
        <Route path="/workflows/:id" element={<WorkflowDetailPage />} />
      </Routes>
    </BrowserRouter>
  )
}
