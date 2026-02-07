import type { NextRequest } from "next/server"
import { NextResponse } from "next/server"

const APEX_DOMAIN = "emergence.quest"
const WWW_DOMAIN = `www.${APEX_DOMAIN}`

export function proxy(request: NextRequest) {
  const forwardedHost = request.headers.get("x-forwarded-host")
  const host = (forwardedHost || request.headers.get("host") || request.nextUrl.host).split(":")[0].toLowerCase()
  const proto = (request.headers.get("x-forwarded-proto") || request.nextUrl.protocol.replace(":", "")).toLowerCase()

  const isProductionHost = host === APEX_DOMAIN || host === WWW_DOMAIN
  if (!isProductionHost) return NextResponse.next()

  const shouldRedirectToWww = host === APEX_DOMAIN
  const shouldRedirectToHttps = proto !== "https"
  if (!shouldRedirectToWww && !shouldRedirectToHttps) return NextResponse.next()

  const destination = new URL(request.nextUrl.pathname + request.nextUrl.search, `https://${WWW_DOMAIN}`)
  return NextResponse.redirect(destination, 308)
}

export const config = {
  matcher: ["/:path*"],
}
