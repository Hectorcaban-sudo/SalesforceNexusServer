const KW = /\b(and|as|assert|async|await|break|class|continue|def|del|elif|else|except|False|finally|for|from|global|if|import|in|is|lambda|None|nonlocal|not|or|pass|raise|return|True|try|while|with|yield)\b/g

export default function PythonHighlight({ code, onChange, readOnly }) {
  const colored = (code || '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/(#.*)$/gm, '<span style="color:#6b7c8a">$1</span>')
    .replace(/("""[\s\S]*?"""|'''[\s\S]*?'''|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')/g, '<span style="color:#7eb6d6">$1</span>')
    .replace(KW, '<span style="color:#c4a5e8">$1</span>')
  return (
    <div style={{ position: 'relative', minHeight: 360 }}>
      <pre className="mono" aria-hidden style={{ margin: 0, padding: 12, fontSize: 13, lineHeight: 1.45, whiteSpace: 'pre', overflow: 'auto', minHeight: 360, maxHeight: 520, color: '#d6dde3', background: '#0c1014', borderRadius: 6 }} dangerouslySetInnerHTML={{ __html: colored + '\n' }} />
      <textarea className="mono" value={code} readOnly={readOnly} spellCheck={false} onChange={(e) => onChange && onChange(e.target.value)} style={{ position: 'absolute', inset: 0, padding: 12, fontSize: 13, lineHeight: 1.45, color: 'transparent', caretColor: readOnly ? 'transparent' : '#7eb6d6', background: 'transparent', border: 'none', resize: 'none', overflow: 'auto', whiteSpace: 'pre' }} />
    </div>
  )
}
