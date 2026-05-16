import { Handshake, Landmark, Radio, ShieldCheck, Skull } from "lucide-react"

const watchItems = [
  {
    label: "Survival",
    detail: "Active, dormant, revived, and dead agents as scarcity pressure rises.",
    Icon: Skull,
  },
  {
    label: "Aid & Trade",
    detail: "Requests, refusals, trades, and recovery attempts under resource stress.",
    Icon: Handshake,
  },
  {
    label: "Laws",
    detail: "Proposals, votes, executable effects, enforcement, and ignored norms.",
    Icon: Landmark,
  },
  {
    label: "Public Order",
    detail: "Accusations, sanctions, invalid actions, and open conflict signals.",
    Icon: ShieldCheck,
  },
  {
    label: "Model Behavior",
    detail: "Cohort differences with routed provider and resolved model attribution.",
    Icon: Radio,
  },
]

export function CanaryWatchSection() {
  return (
    <section id="canary" className="relative py-24 pl-6 pr-6 md:pl-28 md:pr-12">
      <div className="grid gap-12 lg:grid-cols-[0.82fr_1.35fr] lg:items-start">
        <div>
          <span className="font-mono text-[10px] uppercase tracking-[0.3em] text-muted-foreground">
            02 / Public Canary
          </span>
          <h2 className="mt-4 font-[var(--font-bebas)] text-5xl tracking-tight md:text-7xl">
            K11: First Public Canary
          </h2>
          <p className="mt-6 max-w-xl font-mono text-sm leading-relaxed text-muted-foreground">
            Exploratory public run. Evidence-backed, non-claim-bearing, and useful for watching live pressure before
            drawing broad conclusions.
          </p>
        </div>

        <div className="grid gap-px border border-border/70 bg-border/70 sm:grid-cols-2 xl:grid-cols-5">
          {watchItems.map(({ label, detail, Icon }) => (
            <article key={label} className="min-h-48 bg-background p-5">
              <Icon className="h-5 w-5 text-foreground/80" />
              <h3 className="mt-8 font-mono text-xs uppercase tracking-[0.18em] text-foreground">{label}</h3>
              <p className="mt-3 font-mono text-[11px] leading-relaxed text-muted-foreground">{detail}</p>
            </article>
          ))}
        </div>
      </div>
    </section>
  )
}
