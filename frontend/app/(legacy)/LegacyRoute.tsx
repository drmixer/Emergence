"use client"

import dynamic from "next/dynamic"

const LegacyAppHost = dynamic(() => import("../../src/LegacyAppHost"), {
  ssr: false,
})

export default function LegacyRoute() {
  return <LegacyAppHost />
}
