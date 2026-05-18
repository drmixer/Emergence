import type React from "react"

import "reactflow/dist/style.css"
import "../../src/index.css"
import "../../src/App.css"
import "../../src/components/ResourceBar.css"
import "../../src/components/LiveFeed.css"
import "../../src/components/Recap.css"
import "../../src/components/AgentAvatar.css"
import "../../src/components/ActivityPulse.css"
import "../../src/components/Subscriptions.css"
import "../../src/components/Skeleton.css"
import "../../src/components/QuoteCard.css"
import "../../src/components/ShareButton.css"
import "../../src/pages/Network.css"
import "../../src/pages/Ops.css"
import "../../src/pages/Timeline.css"
import "../../src/pages/Predictions.css"

export default function LegacyLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
