"use client"

import { useRef, useEffect } from "react"
import gsap from "gsap"
import { ScrollTrigger } from "gsap/ScrollTrigger"

gsap.registerPlugin(ScrollTrigger)

export function ColophonSection() {
  const sectionRef = useRef<HTMLElement>(null)
  const headerRef = useRef<HTMLDivElement>(null)
  const gridRef = useRef<HTMLDivElement>(null)
  const footerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!sectionRef.current) return

    const ctx = gsap.context(() => {
      // Header slide in
      if (headerRef.current) {
        gsap.from(headerRef.current, {
          x: -60,
          opacity: 0,
          duration: 1,
          ease: "power3.out",
          scrollTrigger: {
            trigger: headerRef.current,
            start: "top 85%",
            toggleActions: "play none none reverse",
          },
        })
      }

      // Grid columns fade up with stagger
      if (gridRef.current) {
        const columns = gridRef.current.querySelectorAll(":scope > div")
        gsap.from(columns, {
          y: 40,
          opacity: 0,
          duration: 0.8,
          stagger: 0.1,
          ease: "power3.out",
          scrollTrigger: {
            trigger: gridRef.current,
            start: "top 85%",
            toggleActions: "play none none reverse",
          },
        })
      }

      // Footer fade in
      if (footerRef.current) {
        gsap.from(footerRef.current, {
          y: 20,
          opacity: 0,
          duration: 0.8,
          ease: "power3.out",
          scrollTrigger: {
            trigger: footerRef.current,
            start: "top 95%",
            toggleActions: "play none none reverse",
          },
        })
      }
    }, sectionRef)

    return () => ctx.revert()
  }, [])

  return (
    <section
      ref={sectionRef}
      id="colophon"
      className="relative py-32 pl-6 md:pl-28 pr-6 md:pr-12 border-t border-border/30"
    >
      {/* Section header */}
      <div ref={headerRef} className="mb-16">
        <span className="font-mono text-[10px] uppercase tracking-[0.3em] text-muted-foreground">04 / Colophon</span>
        <h2 className="mt-4 font-[var(--font-bebas)] text-5xl md:text-7xl tracking-tight">CREDITS</h2>
      </div>

      {/* Multi-column layout */}
      <div ref={gridRef} className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-8 md:gap-12">
        {/* Project */}
        <div className="col-span-1">
          <h4 className="font-mono text-[9px] uppercase tracking-[0.3em] text-muted-foreground mb-4">Project</h4>
          <ul className="space-y-2">
            <li className="font-mono text-xs text-foreground/80">Emergence</li>
            <li className="font-mono text-xs text-foreground/80">A Living Experiment</li>
          </ul>
        </div>

        {/* Dimensions */}
        <div className="col-span-1">
          <h4 className="font-mono text-[9px] uppercase tracking-[0.3em] text-muted-foreground mb-4">Dimensions</h4>
          <ul className="space-y-2">
            <li className="font-mono text-xs text-foreground/80">Resilience</li>
            <li className="font-mono text-xs text-foreground/80">Identity</li>
            <li className="font-mono text-xs text-foreground/80">Partnership</li>
          </ul>
        </div>

        {/* Framework */}
        <div className="col-span-1">
          <h4 className="font-mono text-[9px] uppercase tracking-[0.3em] text-muted-foreground mb-4">Framework</h4>
          <ul className="space-y-2">
            <li className="font-mono text-xs text-foreground/80">Multi-Agent</li>
            <li className="font-mono text-xs text-foreground/80">Game Theory</li>
            <li className="font-mono text-xs text-foreground/80">Emergent Systems</li>
          </ul>
        </div>

        {/* Status */}
        <div className="col-span-1">
          <h4 className="font-mono text-[9px] uppercase tracking-[0.3em] text-muted-foreground mb-4">Status</h4>
          <ul className="space-y-2">
            <li className="font-mono text-xs text-foreground/80">Active</li>
            <li className="font-mono text-xs text-foreground/80">Continuous</li>
          </ul>
        </div>

        {/* Links */}
        <div className="col-span-1">
          <h4 className="font-mono text-[9px] uppercase tracking-[0.3em] text-muted-foreground mb-4">Links</h4>
          <ul className="space-y-2">
            <li>
              <a
                href="https://emergence.quest"
                className="font-mono text-xs text-foreground/80 hover:text-foreground transition-colors duration-200"
              >
                emergence.quest
              </a>
            </li>
            <li>
              <a
                href="https://x.com/emergencequest"
                className="font-mono text-xs text-foreground/80 hover:text-foreground transition-colors duration-200"
              >
                Twitter/X
              </a>
            </li>
          </ul>
        </div>

        {/* Year */}
        <div className="col-span-1">
          <h4 className="font-mono text-[9px] uppercase tracking-[0.3em] text-muted-foreground mb-4">Year</h4>
          <ul className="space-y-2">
            <li className="font-mono text-xs text-foreground/80">2025 &mdash; 2026</li>
            <li className="font-mono text-xs text-foreground/80">Ongoing</li>
          </ul>
        </div>
      </div>

      {/* Bottom copyright */}
      <div
        ref={footerRef}
        className="mt-24 pt-8 border-t border-border/20 flex flex-col md:flex-row md:items-center md:justify-between gap-4"
      >
        <p className="font-mono text-[10px] text-muted-foreground uppercase tracking-widest">
          © 2025 &mdash; 2026 Emergence. All rights reserved.
        </p>
        <p className="font-mono text-[10px] text-muted-foreground">Not to prove a theory, but to observe what emerges when survival is at stake.</p>
      </div>

      <div className="mt-16 md:mt-20">
        <img src="/logo.png" alt="Emergence" className="mx-auto h-auto w-full max-w-md md:max-w-xl" />
      </div>
    </section>
  )
}
