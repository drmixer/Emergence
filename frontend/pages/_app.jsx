import { Bebas_Neue, IBM_Plex_Mono, IBM_Plex_Sans } from 'next/font/google'
import { createElement } from 'react'

import 'reactflow/dist/style.css'
import '../src/index.css'
import '../src/App.css'
import '../src/components/ResourceBar.css'
import '../src/components/LiveFeed.css'
import '../src/components/Recap.css'
import '../src/components/AgentAvatar.css'
import '../src/components/ActivityPulse.css'
import '../src/components/Subscriptions.css'
import '../src/components/Skeleton.css'
import '../src/components/QuoteCard.css'
import '../src/components/ShareButton.css'
import '../src/pages/Network.css'
import '../src/pages/Ops.css'
import '../src/pages/Timeline.css'
import '../src/pages/Predictions.css'

const sans = IBM_Plex_Sans({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
  variable: '--font-landing-sans',
})

const mono = IBM_Plex_Mono({
  subsets: ['latin'],
  weight: ['400', '500'],
  variable: '--font-landing-mono',
})

const display = Bebas_Neue({
  subsets: ['latin'],
  weight: '400',
  variable: '--font-landing-display',
})

export default function EmergenceApp({ Component, pageProps }) {
  return (
    <div className={`${sans.variable} ${mono.variable} ${display.variable}`}>
      {createElement(Component, pageProps)}
    </div>
  )
}
