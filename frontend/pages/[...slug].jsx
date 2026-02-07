import dynamic from 'next/dynamic'

const LegacyAppHost = dynamic(() => import('../src/LegacyAppHost'), { ssr: false })

export default function LegacyCatchAllPage() {
  return <LegacyAppHost />
}
