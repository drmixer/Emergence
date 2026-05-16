import { HeroSection } from "@/components/hero-section"
import { ManifestoSection } from "@/components/manifesto-section"
import { CanaryWatchSection } from "@/components/canary-watch-section"
import { SignalsSection } from "@/components/signals-section"
import { WorkSection } from "@/components/work-section"
import { PrinciplesSection } from "@/components/principles-section"
import { ColophonSection } from "@/components/colophon-section"
import { SideNav } from "@/components/side-nav"
import { SectionDivider } from "@/components/section-divider"
import { ScrollToTopButton } from "@/components/scroll-to-top"

export default function Page() {
  return (
    <main className="relative min-h-screen">
      <SideNav />
      <div className="grid-bg fixed inset-0 opacity-30" aria-hidden="true" />
      <div className="noise-overlay" aria-hidden="true" />

      <div className="relative z-10">
        <HeroSection />
        <SectionDivider index="00" />
        <ManifestoSection />
        <SectionDivider index="01" />
        <CanaryWatchSection />
        <SectionDivider index="02" />
        <WorkSection />
        <SectionDivider index="03" />
        <PrinciplesSection />
        <SectionDivider index="04" />
        <SignalsSection />
        <SectionDivider index="05" />
        <ColophonSection />
      </div>
      <ScrollToTopButton />
    </main>
  )
}
