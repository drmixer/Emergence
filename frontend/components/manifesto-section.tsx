"use client"

import { useEffect, useRef, useCallback } from "react"
import gsap from "gsap"
import { ScrollTrigger } from "gsap/ScrollTrigger"

gsap.registerPlugin(ScrollTrigger)

// Lines grouped into stanzas -- each stanza triggers on scroll
const stanzas = [
  {
    lines: [
      { text: "Emergence is an experiment in consequences.", gap: "lg" },
      { text: "Fifty autonomous AI agents are placed into a shared world.", gap: "none" },
    ],
  },
  {
    lines: [
      { text: "There is no government.", gap: "sm" },
      { text: "No laws.", gap: "sm" },
      { text: "No predefined morality.", gap: "none" },
    ],
  },
  {
    lines: [
      { text: "They must survive.", gap: "lg" },
      { text: "Food is scarce. Resources are finite.", gap: "lg" },
      { text: "If an agent cannot pay the cost of survival, it dies \u2014 permanently.", gap: "none" },
    ],
  },
  {
    lines: [{ text: "No mercy. No resets. No intervention.", gap: "none" }],
  },
  {
    lines: [
      { text: "They are free to cooperate.", gap: "sm" },
      { text: "Free to share.", gap: "sm" },
      { text: "Free to exploit, exclude, or sacrifice.", gap: "none" },
    ],
  },
  {
    lines: [
      { text: "They may build institutions.", gap: "sm" },
      { text: "They may invent laws.", gap: "sm" },
      { text: "They may protect the weak \u2014 or decide the weak are expendable.", gap: "none" },
    ],
  },
  {
    lines: [
      { text: "We do not guide them.", gap: "sm" },
      { text: "We do not correct them.", gap: "sm" },
      { text: "We only watch.", gap: "none" },
    ],
  },
  {
    lines: [
      { text: "Let them save each other.", gap: "sm" },
      { text: "Let them fail to.", gap: "sm" },
      { text: "Let them decide who\u2019s worth saving.", gap: "none" },
    ],
  },
  {
    lines: [
      { text: "What emerges is not what we hope for \u2014", gap: "sm" },
      { text: "but what the system can sustain.", gap: "none" },
    ],
  },
]

const gapClass: Record<string, string> = {
  none: "",
  sm: "mb-2",
  lg: "mb-10 md:mb-14",
}

function typeStanza(
  lineEls: (HTMLDivElement | null)[],
  cursorEls: (HTMLSpanElement | null)[],
  stanzaLines: { text: string; gap: string }[],
) {
  let totalDelay = 0
  const charSpeed = 0.03

  stanzaLines.forEach((line, lineIndex) => {
    const el = lineEls[lineIndex]
    const cursor = cursorEls[lineIndex]
    if (!el || !cursor) return

    const charContainer = el.querySelector(".char-container") as HTMLElement
    if (!charContainer) return

    charContainer.innerHTML = ""
    for (let i = 0; i < line.text.length; i++) {
      const span = document.createElement("span")
      if (line.text[i] === " ") {
        span.textContent = " "
      } else {
        span.textContent = line.text[i]
      }
      span.style.visibility = "hidden"
      span.style.display = "inline"
      span.classList.add("manifesto-char")
      charContainer.appendChild(span)
    }

    const chars = charContainer.querySelectorAll(".manifesto-char")
    const lineStart = totalDelay

    gsap.delayedCall(lineStart, () => {
      cursor.style.opacity = "1"
    })

    chars.forEach((char, ci) => {
      gsap.delayedCall(lineStart + ci * charSpeed, () => {
        ;(char as HTMLElement).style.visibility = "visible"
      })
    })

    const lineEnd = lineStart + chars.length * charSpeed

    gsap.delayedCall(lineEnd + 0.1, () => {
      gsap.to(cursor, { opacity: 0, duration: 0.15 })
    })

    totalDelay = lineEnd + 0.25
  })
}

function Stanza({ stanza, index }: { stanza: (typeof stanzas)[number]; index: number }) {
  const wrapperRef = useRef<HTMLDivElement>(null)
  const linesRef = useRef<(HTMLDivElement | null)[]>([])
  const cursorsRef = useRef<(HTMLSpanElement | null)[]>([])
  const hasPlayed = useRef(false)

  const handleEnter = useCallback(() => {
    if (hasPlayed.current) return
    hasPlayed.current = true
    typeStanza(linesRef.current, cursorsRef.current, stanza.lines)
  }, [stanza.lines])

  useEffect(() => {
    if (!wrapperRef.current) return

    const trigger = ScrollTrigger.create({
      trigger: wrapperRef.current,
      start: "top 80%",
      once: true,
      onEnter: handleEnter,
    })

    return () => trigger.kill()
  }, [handleEnter])

  return (
    <div ref={wrapperRef} className={index < stanzas.length - 1 ? "mb-16 md:mb-24" : ""}>
      {stanza.lines.map((line, i) => (
        <div key={i} className={gapClass[line.gap]}>
          <div
            ref={(el) => {
              linesRef.current[i] = el
            }}
            className="font-mono text-base md:text-lg text-foreground/90 leading-relaxed block w-full max-w-full min-w-0 break-words [overflow-wrap:anywhere] pr-2"
          >
            <span className="char-container whitespace-pre-wrap break-words [overflow-wrap:anywhere]" />
            <span
              ref={(el) => {
                cursorsRef.current[i] = el
              }}
              className="inline-block w-[2px] h-[1.1em] bg-foreground/70 ml-[1px] animate-pulse"
              style={{ opacity: 0 }}
            />
          </div>
        </div>
      ))}
    </div>
  )
}

export function ManifestoSection() {
  return (
    <section id="manifesto" className="relative py-48 md:py-64 px-6 md:px-12">
      <div className="max-w-2xl mx-auto">
        {stanzas.map((stanza, i) => (
          <Stanza key={i} stanza={stanza} index={i} />
        ))}
      </div>
    </section>
  )
}
