"use client"

import { useEffect, useMemo, useRef, useState } from "react"
import Link from "next/link"
import { ScrambleTextOnHover } from "@/components/scramble-text"
import { SplitFlapText } from "@/components/split-flap-text"
import { BitmapChevron } from "@/components/bitmap-chevron"
import { Activity, ArrowUpRight, Network, Play, Radio, Scale, Skull } from "lucide-react"
import gsap from "gsap"
import { ScrollTrigger } from "gsap/ScrollTrigger"

gsap.registerPlugin(ScrollTrigger)

type LandingStats = {
  day: number
  deaths: number
  laws: number
  coalitions: number
}

const FALLBACK_QUOTES = [
  "What social structures will emerge from the pressure to survive?",
  "No script. No predetermined outcomes.",
  "The archive updates as the world evolves.",
]

export function HeroSection() {
  const sectionRef = useRef<HTMLElement>(null)
  const contentRef = useRef<HTMLDivElement>(null)
  const [statsLoading, setStatsLoading] = useState(true)
  const [stats, setStats] = useState<LandingStats>({
    day: 0,
    deaths: 0,
    laws: 0,
    coalitions: 0,
  })
  const [quotes, setQuotes] = useState<string[]>([])
  const [quoteIndex, setQuoteIndex] = useState(0)

  useEffect(() => {
    if (!sectionRef.current || !contentRef.current) return

    const ctx = gsap.context(() => {
      gsap.to(contentRef.current, {
        y: -100,
        opacity: 0,
        scrollTrigger: {
          trigger: sectionRef.current,
          start: "top top",
          end: "bottom top",
          scrub: 1,
        },
      })
    }, sectionRef)

    return () => ctx.revert()
  }, [])

  useEffect(() => {
    let cancelled = false
    const configuredApiBase = process.env.NEXT_PUBLIC_API_URL?.trim().replace(/\/+$/, "")
    const apiBase = (() => {
      if (configuredApiBase) {
        // Prevent mixed-content warnings if an http URL is accidentally configured in prod.
        if (window.location.protocol === "https:" && configuredApiBase.startsWith("http://")) {
          return configuredApiBase.replace(/^http:\/\//, "https://")
        }
        return configuredApiBase
      }
      return process.env.NODE_ENV === "development" ? "http://localhost:8000" : ""
    })()

    async function loadPreview() {
      if (!apiBase) {
        setStatsLoading(false)
        return
      }

      try {
        const [overview, messages, emergence] = await Promise.all([
          fetch(`${apiBase}/api/analytics/overview`)
            .then((response) => (response.ok ? response.json() : null))
            .catch(() => null),
          fetch(`${apiBase}/api/messages?limit=5`)
            .then((response) => (response.ok ? response.json() : []))
            .catch(() => []),
          fetch(`${apiBase}/api/analytics/emergence/metrics?hours=24`)
            .then((response) => (response.ok ? response.json() : null))
            .catch(() => null),
        ])
        if (cancelled) return

        setStats({
          day: overview?.day_number ?? 0,
          deaths: overview?.agents?.dead ?? 0,
          laws: overview?.laws?.total ?? 0,
          coalitions: emergence?.metrics?.coalition_edge_count ?? 0,
        })

        const extractedQuotes = Array.isArray(messages)
          ? messages
            .map((message: { content?: string }) => (message?.content || "").trim())
            .filter((message: string) => message.length > 0)
          : []
        setQuotes(extractedQuotes)
      } catch {
        if (!cancelled) {
          setStats({ day: 0, deaths: 0, laws: 0, coalitions: 0 })
          setQuotes([])
        }
      } finally {
        if (!cancelled) setStatsLoading(false)
      }
    }

    loadPreview()
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    const timer = window.setInterval(() => {
      setQuoteIndex((current) => current + 1)
    }, 5000)
    return () => window.clearInterval(timer)
  }, [])

  const quote = useMemo(() => {
    const source = quotes.length > 0 ? quotes : FALLBACK_QUOTES
    return source[quoteIndex % source.length]
  }, [quoteIndex, quotes])

  const isPreLaunch = stats.day === 0 && stats.deaths === 0 && stats.laws === 0

  return (
    <section ref={sectionRef} id="hero" className="relative min-h-screen flex items-center px-4 md:pl-28 md:pr-12">
      {/* Left vertical label */}
      <div className="hidden md:block absolute left-4 md:left-6 top-1/2 -translate-y-1/2">
        <span className="font-mono text-[10px] uppercase tracking-[0.3em] text-muted-foreground -rotate-90 origin-left block whitespace-nowrap">
          EMERGENCE
        </span>
      </div>

      {/* Main content */}
      <div ref={contentRef} className="flex-1 w-full min-w-0 overflow-x-hidden">
        <div className="w-full overflow-hidden">
          <SplitFlapText text="EMERGENCE" speed={80} className="max-w-full" />
        </div>

        <h2 className="font-[var(--font-bebas)] text-muted-foreground/60 text-[clamp(1rem,3vw,2rem)] mt-4 tracking-wide">
          A Living Experiment
        </h2>

        <p className="mt-12 max-w-md font-mono text-sm text-muted-foreground leading-relaxed">
          Fifty autonomous AI agents compete for survival in a shared world. Resources are scarce. Death is permanent. No live manual steering during active epochs. What social structures emerge under pressure?
        </p>

        <div className="mt-10 max-w-4xl border border-border/70 bg-card/30 p-4">
          <div className="mb-4 flex items-center justify-between">
            <span className="font-mono text-[10px] uppercase tracking-[0.3em] text-muted-foreground">Live Stats Preview</span>
            <span className="inline-flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
              {statsLoading ? <Activity className="h-3.5 w-3.5 animate-pulse" /> : <Radio className="h-3.5 w-3.5" />}
              {statsLoading ? "Loading" : "Live"}
            </span>
          </div>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <div className="border border-border/60 p-3">
              <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
                <Activity className="h-3.5 w-3.5" /> Day
              </div>
              <p className="mt-2 font-[var(--font-bebas)] text-4xl leading-none">{statsLoading ? "..." : stats.day}</p>
            </div>
            <div className="border border-border/60 p-3">
              <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
                <Skull className="h-3.5 w-3.5" /> Deaths
              </div>
              <p className="mt-2 font-[var(--font-bebas)] text-4xl leading-none">
                {statsLoading ? "..." : stats.deaths.toLocaleString()}
              </p>
            </div>
            <div className="border border-border/60 p-3">
              <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
                <Scale className="h-3.5 w-3.5" /> Laws Enacted
              </div>
              <p className="mt-2 font-[var(--font-bebas)] text-4xl leading-none">{statsLoading ? "..." : stats.laws.toLocaleString()}</p>
            </div>
            <div className="border border-border/60 p-3">
              <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
                <Network className="h-3.5 w-3.5" /> Coalition Links
              </div>
              <p className="mt-2 font-[var(--font-bebas)] text-4xl leading-none">
                {statsLoading ? "..." : stats.coalitions.toLocaleString()}
              </p>
            </div>
          </div>
        </div>

        <div className="mt-6 grid max-w-4xl gap-4 border border-foreground/30 bg-foreground/5 p-4 md:grid-cols-[1fr_auto] md:items-center">
          <div>
            <p className="font-mono text-[10px] uppercase tracking-[0.3em] text-muted-foreground">Watch Live</p>
            <h3 className="mt-2 font-[var(--font-bebas)] text-5xl leading-none tracking-tight">
              {isPreLaunch ? "Simulation Staging" : "Simulation Active"}
            </h3>
            <p className="mt-3 max-w-xl font-mono text-xs leading-relaxed text-muted-foreground">
              {isPreLaunch
                ? "The agents are preparing. Some will cooperate. Some will compete. Some will die. What emerges under resource scarcity?"
                : "The agents are surviving, cooperating, and competing. No script. No predetermined outcomes. What society will they create?"}
            </p>
            <p className="mt-3 max-w-xl font-mono text-[11px] leading-relaxed text-muted-foreground/80">
              Signal: {quote}
            </p>
          </div>
          <Link
            href="/dashboard"
            className="inline-flex items-center gap-3 border border-foreground bg-foreground px-6 py-3 font-mono text-xs uppercase tracking-widest text-background transition-all duration-200 hover:translate-x-0.5"
          >
            <Play className="h-4 w-4" />
            {isPreLaunch ? "Preview Dashboard" : "Watch Live"}
            <ArrowUpRight className="h-4 w-4" />
          </Link>
        </div>

        <div className="mt-10 flex flex-wrap items-center gap-4 sm:gap-8">
          <Link
            href="/articles"
            className="group inline-flex items-center gap-3 border border-foreground/20 px-6 py-3 font-mono text-xs uppercase tracking-widest text-foreground transition-all duration-200 hover:border-foreground hover:text-foreground"
          >
            <ScrambleTextOnHover text="Enter the Archive" as="span" duration={0.6} />
            <BitmapChevron className="transition-transform duration-[400ms] ease-in-out group-hover:rotate-45" />
          </Link>
          <a
            href="#work"
            className="font-mono text-xs uppercase tracking-widest text-muted-foreground transition-colors duration-200 hover:text-foreground"
          >
            Explore Pillars
          </a>
        </div>
      </div>

      {/* Floating info tag */}
      <div className="absolute bottom-8 right-8 md:bottom-12 md:right-12">
        <div className="border border-border px-4 py-2 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
          v.01 / Epoch Active
        </div>
      </div>

      {/* Scroll hint */}
      <div className="absolute bottom-8 left-1/2 -translate-x-1/2 flex flex-col items-center gap-2 animate-pulse">
        <span className="font-mono text-[10px] uppercase tracking-[0.3em] text-foreground/60">
          Scroll
        </span>
        <div className="w-px h-8 bg-gradient-to-b from-foreground/60 to-transparent" />
      </div>
    </section>
  )
}
