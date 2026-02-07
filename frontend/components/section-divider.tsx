export function SectionDivider({ index }: { index: string }) {
  return (
    <div className="flex items-center gap-4 px-6 md:px-28 py-8" aria-hidden="true">
      <div className="flex-1 h-px bg-foreground/30" />
      <span className="font-mono text-[10px] uppercase tracking-[0.3em] text-foreground/50">
        {index}
      </span>
      <div className="flex-1 h-px bg-foreground/30" />
    </div>
  )
}
