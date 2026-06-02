import { NavLink } from 'react-router-dom'

interface PageHeaderProps {
  actions?: React.ReactNode
}

export const PAGE_CONTENT_WIDTH_CLASS = 'max-w-[1320px] mx-auto'

export function PageHeader({ actions }: PageHeaderProps) {
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
        {actions && <div className="flex items-center gap-2">{actions}</div>}
      </div>
    </div>
  )
}
