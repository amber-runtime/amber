import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

interface Props {
  output: string
}

// Pure markdown renderer. Callers decide when to render.
export function FinalAnswerCard({ output }: Props) {
  return (
    <div className="prose text-sm text-slate-300 max-w-none">
      <Markdown remarkPlugins={[remarkGfm]}>{output}</Markdown>
    </div>
  )
}
