"use client"

import { useRef, useState, useEffect } from "react"
import Link from "next/link"
import { cn } from "@/lib/utils"
import { fetchPublishedArticles, formatArticleDateCompact, getArticles, type Article } from "@/lib/articles"
import gsap from "gsap"
import { ScrollTrigger } from "gsap/ScrollTrigger"

gsap.registerPlugin(ScrollTrigger)

export function SignalsSection() {
  const scrollRef = useRef<HTMLDivElement>(null)
  const sectionRef = useRef<HTMLElement>(null)
  const headerRef = useRef<HTMLDivElement>(null)
  const cardsRef = useRef<HTMLDivElement>(null)
  const cursorRef = useRef<HTMLDivElement>(null)
  const rafRef = useRef<number | null>(null)
  const cursorTargetRef = useRef({ x: 0, y: 0 })
  const [isHovering, setIsHovering] = useState(false)
  const [articles, setArticles] = useState<Article[]>(() => getArticles())

  useEffect(() => {
    if (!sectionRef.current || !cursorRef.current) return

    const section = sectionRef.current
    const cursor = cursorRef.current
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches
    if (reduceMotion) return

    const moveCursorX = gsap.quickTo(cursor, "x", {
      duration: 0.22,
      ease: "power3.out",
    })
    const moveCursorY = gsap.quickTo(cursor, "y", {
      duration: 0.22,
      ease: "power3.out",
    })

    const flushCursorPosition = () => {
      rafRef.current = null
      moveCursorX(cursorTargetRef.current.x)
      moveCursorY(cursorTargetRef.current.y)
    }

    const handleMouseMove = (e: MouseEvent) => {
      const rect = section.getBoundingClientRect()
      cursorTargetRef.current = {
        x: e.clientX - rect.left,
        y: e.clientY - rect.top,
      }

      if (rafRef.current === null) {
        rafRef.current = window.requestAnimationFrame(flushCursorPosition)
      }
    }

    const handleMouseEnter = () => setIsHovering(true)
    const handleMouseLeave = () => setIsHovering(false)

    section.addEventListener("mousemove", handleMouseMove, { passive: true })
    section.addEventListener("mouseenter", handleMouseEnter)
    section.addEventListener("mouseleave", handleMouseLeave)

    return () => {
      if (rafRef.current !== null) {
        window.cancelAnimationFrame(rafRef.current)
        rafRef.current = null
      }
      section.removeEventListener("mousemove", handleMouseMove)
      section.removeEventListener("mouseenter", handleMouseEnter)
      section.removeEventListener("mouseleave", handleMouseLeave)
    }
  }, [])

  useEffect(() => {
    if (!sectionRef.current || !headerRef.current || !cardsRef.current) return

    const ctx = gsap.context(() => {
      // Header slide in from left
      gsap.fromTo(
        headerRef.current,
        { x: -60, opacity: 0 },
        {
          x: 0,
          opacity: 1,
          duration: 1,
          ease: "power3.out",
          scrollTrigger: {
            trigger: headerRef.current,
            start: "top 85%",
            toggleActions: "play none none reverse",
          },
        },
      )

      const cards = cardsRef.current?.querySelectorAll("[data-signal-card]")
      if (cards) {
        gsap.fromTo(
          cards,
          { x: -100, opacity: 0 },
          {
            x: 0,
            opacity: 1,
            duration: 0.8,
            stagger: 0.2,
            ease: "power3.out",
            scrollTrigger: {
              trigger: cardsRef.current,
              start: "top 90%",
              toggleActions: "play none none reverse",
            },
          },
        )
      }
    }, sectionRef)

    return () => ctx.revert()
  }, [])

  useEffect(() => {
    let cancelled = false
    async function loadArticles() {
      const latest = await fetchPublishedArticles(12)
      if (!cancelled) {
        setArticles(latest)
      }
    }
    loadArticles()
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <section id="signals" ref={sectionRef} className="relative py-32 pl-6 md:pl-28">
      <div
        ref={cursorRef}
        className={cn(
          "pointer-events-none absolute top-0 left-0 -translate-x-1/2 -translate-y-1/2 z-50",
          "w-12 h-12 rounded-full border-2 border-foreground bg-foreground",
          "transition-opacity duration-300 will-change-transform",
          isHovering ? "opacity-100" : "opacity-0",
        )}
      />

      {/* Section header */}
      <div ref={headerRef} className="mb-16 pr-6 md:pr-12">
        <span className="font-mono text-[10px] uppercase tracking-[0.3em] text-muted-foreground">01 / Articles</span>
        <h2 className="mt-4 font-[var(--font-bebas)] text-5xl md:text-7xl tracking-tight">FROM THE ARCHIVE</h2>
      </div>

      {/* Horizontal scroll container */}
      <div
        ref={(el) => {
          scrollRef.current = el
          cardsRef.current = el
        }}
        className="flex gap-8 overflow-x-auto pb-8 pr-12 scrollbar-hide"
        style={{ scrollbarWidth: "none", msOverflowStyle: "none" }}
      >
        {articles.length === 0 ? (
          <article data-signal-card className="w-80 flex-shrink-0 border border-border/60 bg-card/50 p-8">
            <p className="font-mono text-[10px] uppercase tracking-[0.3em] text-muted-foreground">No Entries Yet</p>
            <p className="mt-4 font-mono text-xs leading-relaxed text-muted-foreground">
              The archive is active, but no articles have been published yet.
            </p>
          </article>
        ) : (
          articles.map((article, index) => <SignalCard key={article.slug} article={article} index={index} />)
        )}
      </div>
    </section>
  )
}

function SignalCard({
  article,
  index,
}: {
  article: Article
  index: number
}) {
  return (
    <Link
      data-signal-card
      href={`/articles/${article.slug}`}
      className={cn(
        "group relative flex-shrink-0 w-80",
        "transition-transform duration-500 ease-out",
        "hover:-translate-y-2",
      )}
    >
      {/* Card with paper texture effect */}
      <div className="relative bg-card border border-border/50 md:border-t md:border-l md:border-r-0 md:border-b-0 p-8">
        {/* Top torn edge effect */}
        <div className="absolute -top-px left-0 right-0 h-px bg-gradient-to-r from-transparent via-border/40 to-transparent" />

        {/* Issue number - editorial style */}
        <div className="flex items-baseline justify-between mb-8">
          <span className="font-mono text-[10px] uppercase tracking-[0.3em] text-muted-foreground">
            No. {String(index + 1).padStart(2, "0")}
          </span>
          <time className="font-mono text-[10px] text-muted-foreground/60">
            {formatArticleDateCompact(article.publishedAt)}
          </time>
        </div>

        {/* Title */}
        <h3 className="font-[var(--font-bebas)] text-4xl tracking-tight mb-4 group-hover:text-foreground transition-colors duration-300">
          {article.title}
        </h3>

        {/* Divider line */}
        <div className="w-12 h-px bg-foreground/30 mb-6 group-hover:w-full transition-all duration-500" />

        {/* Description */}
        <p className="font-mono text-xs text-muted-foreground leading-relaxed">{article.summary}</p>

        {/* Bottom right corner fold effect */}
        <div className="absolute bottom-0 right-0 w-6 h-6 overflow-hidden">
          <div className="absolute bottom-0 right-0 w-8 h-8 bg-background rotate-45 translate-x-4 translate-y-4 border-t border-l border-border/30" />
        </div>
      </div>

      {/* Shadow/depth layer */}
      <div className="absolute inset-0 -z-10 translate-x-1 translate-y-1 bg-foreground/5 opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
    </Link>
  )
}
