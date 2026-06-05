import { NavLink } from 'react-router-dom'
import { LogOut } from 'lucide-react'
import { useAuth } from '../lib/auth'

interface PageHeaderProps {
  actions?: React.ReactNode
}

export const PAGE_CONTENT_WIDTH_CLASS = 'max-w-[1320px] mx-auto'

export function PageHeader({ actions }: PageHeaderProps) {
  const { authenticated, logout } = useAuth()
  const navClass = ({ isActive }: { isActive: boolean }) =>
    `text-sm font-medium px-1 pb-0.5 border-b-2 transition-colors ${
      isActive
        ? 'text-slate-50 border-amber-500'
        : 'text-slate-400 border-transparent hover:text-slate-200 hover:border-slate-600'
    }`

  return (
    <div className="bg-slate-900 border-b border-slate-800 px-6 py-4">
      <div className={`${PAGE_CONTENT_WIDTH_CLASS} flex items-center justify-between`}>
        <div className="flex items-center gap-4">
          <span className="text-amber-500 font-semibold tracking-tight text-xl">Amber</span>
          <nav className="flex items-center gap-4">
            <NavLink to="/" end className={navClass}>
              Workflows
            </NavLink>
          </nav>
        </div>
        <div className="flex items-center gap-2">
          {actions}
          {authenticated && (
            <button
              type="button"
              aria-label="Sign out"
              title="Sign out"
              onClick={logout}
              className="inline-flex h-8 w-8 items-center justify-center rounded border border-slate-700 text-slate-300 hover:border-slate-500 hover:text-slate-50"
            >
              <LogOut size={15} />
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
