"use client"

import { useEffect, useState } from "react"
import { ArrowUp } from "lucide-react"

export function ScrollToTopButton() {
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    const onScroll = () => {
      const threshold = window.innerHeight * 0.6
      setVisible(window.scrollY > threshold)
    }

    onScroll()
    window.addEventListener("scroll", onScroll, { passive: true })
    return () => window.removeEventListener("scroll", onScroll)
  }, [])

  const scrollToTop = () => {
    window.scrollTo({ top: 0, behavior: "smooth" })
  }

  return (
    <button
      type="button"
      aria-label="Scroll to top"
      onClick={scrollToTop}
      className={[
        "fixed bottom-6 right-6 z-[80] inline-flex h-11 w-11 items-center justify-center",
        "border border-foreground/35 bg-background/85 text-foreground shadow-lg backdrop-blur-sm",
        "transition-all duration-300 hover:-translate-y-0.5 hover:border-foreground hover:bg-background",
        visible ? "pointer-events-auto opacity-100" : "pointer-events-none opacity-0",
      ].join(" ")}
    >
      <ArrowUp className="h-4 w-4" />
    </button>
  )
}
