// Shared library of "starting point" interest ideas — the same chips the
// onboarding interview offers, available permanently via the in-app Ideas panel.
//
// Each idea is a real starting intent. Tapping one spawns a standing watch
// (POST /watches). `prompt(zip)` is a function of an optional zip so location
// ideas ("near me") thread the user's real place when known, else fall back to
// generic phrasing — mirroring the onboarding behavior.
//
// NOTE: Onboarding.tsx keeps its own copy of this list intentionally (it owns
// that file and we must not risk breaking it). Keep the two in rough sync, but
// this module is the canonical one for new surfaces.

export interface Idea {
  label: string; // short chip text
  prompt: (zip: string) => string; // intent sent to the agent; zip is "" if none
}

// "houses near me" → "houses near 77005" when a zip is known, else generic.
const nearZip = (zip: string, withZip: string, generic: string) =>
  zip ? withZip.replace("{zip}", zip) : generic;

export const IDEAS_PERSONAL: Idea[] = [
  {
    label: "Houses near me",
    prompt: (zip) =>
      nearZip(
        zip,
        "Watch Zillow for houses near {zip}",
        "Watch Zillow for houses in my neighborhood",
      ),
  },
  {
    label: "Weather near me",
    prompt: (zip) =>
      nearZip(
        zip,
        "Watch the weather in {zip} and warn me about anything notable",
        "Watch my local weather and warn me about anything notable",
      ),
  },
  { label: "GPU deals", prompt: () => "Track GPU prices and tell me about deals under $500" },
  { label: "What I'm reading", prompt: () => "Keep notes on what I'm reading" },
  { label: "AI agent research", prompt: () => "Follow new research on AI agents" },
];

export const IDEAS_GENERAL: Idea[] = [
  { label: "Flight status", prompt: () => "Track a flight's status and tell me about delays or gate changes" },
  { label: "Flight deals", prompt: () => "Find flight deals to a place I want to go" },
  { label: "Package tracking", prompt: () => "Track a package and tell me when it's out for delivery" },
  { label: "Concert tickets", prompt: () => "Alert me when concert tickets I care about drop" },
  { label: "Price drop", prompt: () => "Watch a product and tell me when the price drops" },
  { label: "Back in stock", prompt: () => "Watch a product until it's back in stock" },
  { label: "News on a topic", prompt: () => "Summarize news on a topic I care about" },
  { label: "A stock or crypto", prompt: () => "Track a stock or crypto for me" },
  {
    label: "Apartments near me",
    prompt: (zip) =>
      nearZip(
        zip,
        "Find apartments near {zip} within a budget",
        "Find apartments under a budget",
      ),
  },
];

export const ALL_IDEAS: Idea[] = [...IDEAS_PERSONAL, ...IDEAS_GENERAL];

// localStorage key the Ideas panel uses to remember a zip for "near me" ideas.
// Self-sufficient: onboarding distills zip to the vault, not localStorage, so the
// panel lets the user set/confirm it here and persists it for next time.
export const ZIP_KEY = "gardener_zip";
