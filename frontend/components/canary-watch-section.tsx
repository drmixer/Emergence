import { Handshake, Landmark, Radio, ShieldCheck, Skull } from "lucide-react"
import { getPublicRunFraming } from "@/lib/public-run-framing"

const watchIcons = {
  Survival: Skull,
  "Aid & Trade": Handshake,
  "Aid & trade": Handshake,
  Laws: Landmark,
  "Public Order": ShieldCheck,
  "Model Behavior": Radio,
  "Model behavior": Radio,
}

export function CanaryWatchSection() {
  const framing = getPublicRunFraming()

  return (
    <section id="canary" className="relative py-24 pl-6 pr-6 md:pl-28 md:pr-12">
      <div className="grid gap-12 lg:grid-cols-[0.82fr_1.35fr] lg:items-start">
        <div>
          <span className="font-mono text-[10px] uppercase tracking-[0.3em] text-muted-foreground">
            02 / Public Canary
          </span>
          <h2 className="mt-4 font-[var(--font-bebas)] text-5xl tracking-tight md:text-7xl">
            {framing.label}
          </h2>
          <p className="mt-6 max-w-xl font-mono text-sm leading-relaxed text-muted-foreground">
            {framing.sectionNote}
          </p>
        </div>

        <div className="grid gap-px border border-border/70 bg-border/70 sm:grid-cols-2 xl:grid-cols-5">
          {framing.watchItems.map(({ label, detail }) => {
            const Icon = watchIcons[label as keyof typeof watchIcons] || ShieldCheck
            return (
              <article key={label} className="min-h-48 bg-background p-5">
                <Icon className="h-5 w-5 text-foreground/80" />
                <h3 className="mt-8 font-mono text-xs uppercase tracking-[0.18em] text-foreground">{label}</h3>
                <p className="mt-3 font-mono text-[11px] leading-relaxed text-muted-foreground">{detail}</p>
              </article>
            )
          })}
        </div>
      </div>
    </section>
  )
}
