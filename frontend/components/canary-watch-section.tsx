import { Handshake, Landmark, Radio, ShieldCheck, Skull } from "lucide-react"
import { getPublicRunFraming } from "@/lib/public-run-framing"
import { getRunSchedule } from "@/src/data/runSchedule"

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
  const plannedCanaries = getRunSchedule()
    .filter((run) => run.track === "Public Canary" && ["K12", "K13", "K14", "K15"].includes(run.label))
    .slice(0, 4)

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

      {plannedCanaries.length > 0 && (
        <div className="mt-14 border-t border-border/70 pt-8">
          <div className="grid gap-8 lg:grid-cols-[0.82fr_1.35fr] lg:items-start">
            <div>
              <p className="font-mono text-[10px] uppercase tracking-[0.3em] text-muted-foreground">
                Planned public slate
              </p>
              <h3 className="mt-3 font-[var(--font-bebas)] text-4xl tracking-tight md:text-5xl">
                Questions before runs
              </h3>
              <p className="mt-4 max-w-lg font-mono text-xs leading-relaxed text-muted-foreground">
                The next canaries are planned as distinct viewer-facing tests so each run has a reason to exist before it starts.
              </p>
            </div>

            <div className="grid gap-px border border-border/70 bg-border/70 md:grid-cols-2">
              {plannedCanaries.map((run) => (
                <article key={run.id} className="min-h-44 bg-background p-5">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted-foreground">
                        {run.planningState}
                      </p>
                      <h4 className="mt-2 font-mono text-sm uppercase tracking-[0.16em] text-foreground">
                        {run.label}: {run.theme}
                      </h4>
                    </div>
                    <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                      {run.status}
                    </span>
                  </div>
                  <p className="mt-5 font-mono text-[11px] leading-relaxed text-muted-foreground">
                    {run.declaredQuestion}
                  </p>
                </article>
              ))}
            </div>
          </div>
        </div>
      )}
    </section>
  )
}
