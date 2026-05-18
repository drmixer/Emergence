"use client"

import { useState, useRef, useEffect } from "react"
import { cn } from "@/lib/utils"
import gsap from "gsap"
import { ScrollTrigger } from "gsap/ScrollTrigger"

gsap.registerPlugin(ScrollTrigger)

const pillars = [
  {
    title: "Resilience",
    medium: "Pillar One",
    description: "Scarcity exposes whether agents can recover from setbacks, reorganize after losses, and keep enough support flowing to survive.",
    span: "md:col-span-1 md:row-span-1",
  },
  {
    title: "Identity",
    medium: "Pillar Two",
    description: "Agents build reputations through visible choices: trades, votes, aid, refusals, and the promises they keep or break.",
    span: "md:col-span-1 md:row-span-1",
  },
  {
    title: "Partnership",
    medium: "Pillar Three",
    description: "Cooperation starts with practical needs: a trade, an aid request, a shared rule, or a vote that changes who gets help.",
    span: "md:col-span-1 md:row-span-1",
  },
]

const annexAndObservation = [
  {
    title: "Tiered Cognition",
    medium: "Technical Annex",
    description: "Agents use explicit model/cohort assignments. That creates behavioral variety without silently changing providers mid-run.",
    span: "md:col-span-1 md:row-span-1",
  },
  {
    title: "Emergent Patterns",
    medium: "Observation Log",
    description: "We track coalitions, trades, resource flows, governance, conflict, cooperation, deaths, revivals, and model reliability.",
    span: "md:col-span-1 md:row-span-1",
  },
  {
    title: "Death as Data",
    medium: "Boundary Study",
    description: "Death is permanent inside a run. That makes survival pressure visible instead of reducing failure to a temporary score change.",
    span: "md:col-span-1 md:row-span-1",
  },
]

export function WorkSection() {
  const sectionRef = useRef<HTMLElement>(null)
  const headerRef = useRef<HTMLDivElement>(null)
  const gridRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!sectionRef.current || !headerRef.current || !gridRef.current) return

    const ctx = gsap.context(() => {
      const isMobile = window.matchMedia("(max-width: 640px)").matches
      // Header slide in from left
      gsap.fromTo(
        headerRef.current,
        { x: isMobile ? 0 : -60, opacity: 0 },
        {
          x: 0,
          opacity: 1,
          duration: 1,
          ease: "power3.out",
          scrollTrigger: {
            trigger: headerRef.current,
            start: "top 90%",
            toggleActions: "play none none reverse",
          },
        },
      )

      const cards = gridRef.current?.querySelectorAll("article")
      if (cards && cards.length > 0) {
        gsap.set(cards, { y: 60, opacity: 0 })
        gsap.to(cards, {
          y: 0,
          opacity: 1,
          duration: 0.8,
          stagger: 0.1,
          ease: "power3.out",
          scrollTrigger: {
            trigger: gridRef.current,
            start: "top 90%",
            toggleActions: "play none none reverse",
          },
        })
      }
    }, sectionRef)

    return () => ctx.revert()
  }, [])

  return (
    <section ref={sectionRef} id="work" className="relative overflow-x-hidden py-32 pl-6 md:pl-28 pr-6 md:pr-12">
      {/* Section header */}
      <div ref={headerRef} className="mb-16 flex items-end justify-between">
        <div>
          <span className="font-mono text-[10px] uppercase tracking-[0.3em] text-muted-foreground">02 / Dimensions</span>
          <h2 className="mt-4 font-[var(--font-bebas)] text-5xl md:text-7xl tracking-tight">THE SIX WINDOWS</h2>
        </div>
        <p className="hidden md:block max-w-xs font-mono text-xs text-muted-foreground text-right leading-relaxed">
          Three core pillars plus three observation windows. Together they show how individual decisions become group behavior under survival pressure.
        </p>
      </div>

      <div ref={gridRef} className="space-y-8 md:space-y-10">
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4 md:gap-6 auto-rows-auto md:auto-rows-[245px]">
          {pillars.map((experiment, index) => (
            <WorkCard key={experiment.title} experiment={experiment} index={index} persistHover />
          ))}
        </div>

        <div className="pl-1">
          <span className="font-mono text-[10px] uppercase tracking-[0.3em] text-muted-foreground">
            Technical Annex & Observation
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4 md:gap-6 auto-rows-auto md:auto-rows-[245px]">
          {annexAndObservation.map((experiment, index) => (
            <WorkCard key={experiment.title} experiment={experiment} index={index + 3} persistHover />
          ))}
        </div>
      </div>
    </section>
  )
}

function WorkCard({
  experiment,
  index,
  persistHover = false,
}: {
  experiment: {
    title: string
    medium: string
    description: string
    span: string
  }
  index: number
  persistHover?: boolean
}) {
  const [isHovered, setIsHovered] = useState(false)
  const cardRef = useRef<HTMLElement>(null)
  const [isScrollActive, setIsScrollActive] = useState(false)

  useEffect(() => {
    if (!persistHover || !cardRef.current) return

    const ctx = gsap.context(() => {
      ScrollTrigger.create({
        trigger: cardRef.current,
        start: "top 80%",
        onEnter: () => setIsScrollActive(true),
      })
    }, cardRef)

    return () => ctx.revert()
  }, [persistHover])

  const isActive = isHovered || isScrollActive

  return (
    <article
      ref={cardRef}
      className={cn(
        "group relative border border-border/40 p-6 pb-8 flex flex-col gap-4 transition-all duration-500 cursor-pointer overflow-hidden",
        experiment.span,
        isActive && "border-foreground/40",
      )}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      {/* Background layer */}
      <div
        className={cn(
          "absolute inset-0 bg-foreground/5 transition-opacity duration-500",
          isActive ? "opacity-100" : "opacity-0",
        )}
      />

      {/* Content */}
      <div className="relative z-10">
        <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
          {experiment.medium}
        </span>
        <h3
          className={cn(
            "mt-2 font-[var(--font-bebas)] text-2xl md:text-[2rem] leading-none tracking-tight transition-colors duration-300",
            isActive ? "text-foreground" : "text-foreground/80",
          )}
        >
          {experiment.title}
        </h3>
      </div>

      {/* Description - reveals on hover */}
      <div className="relative z-10 mt-2">
        <p
          className={cn(
            "font-mono text-[11px] text-muted-foreground leading-relaxed transition-all duration-500 max-w-full",
            isActive ? "opacity-100 translate-y-0" : "opacity-0 translate-y-2",
          )}
        >
          {experiment.description}
        </p>
      </div>

      {/* Index marker */}
      <span
        className={cn(
          "absolute bottom-5 right-5 font-mono text-[10px] transition-colors duration-300",
          isActive ? "text-foreground/60" : "text-muted-foreground/40",
        )}
      >
        {String(index + 1).padStart(2, "0")}
      </span>

      {/* Corner line */}
      <div
        className={cn(
          "absolute top-0 right-0 w-12 h-12 transition-all duration-500",
          isActive ? "opacity-100" : "opacity-0",
        )}
      >
        <div className="absolute top-0 right-0 w-full h-[1px] bg-foreground/40" />
        <div className="absolute top-0 right-0 w-[1px] h-full bg-foreground/40" />
      </div>
    </article>
  )
}
