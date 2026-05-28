import type { ReactElement } from 'react'
import { render } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

export function renderWithRoute(
  ui: ReactElement,
  options: { route?: string; path?: string } = {},
) {
  const route = options.route ?? '/'
  const path = options.path ?? '/'
  return render(
    <MemoryRouter initialEntries={[route]}>
      <Routes>
        <Route path={path} element={ui} />
      </Routes>
    </MemoryRouter>,
  )
}
