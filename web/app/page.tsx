"use client";

import { useEffect, useState } from "react";
import { MotionConfig } from "framer-motion";
import { getWatches, type Watch } from "@/lib/api";
import { usePolling } from "@/lib/hooks";
import Sidebar from "@/components/Sidebar";
import ChatPane from "@/components/ChatPane";
import RightRail from "@/components/RightRail";
import OfflineBanner from "@/components/OfflineBanner";
import Onboarding, { ONBOARDED_KEY } from "@/components/Onboarding";

export default function Home() {
  // "main" or a watch id
  const [selected, setSelected] = useState("main");
  // text pushed into the composer when a garden fact is clicked
  const [injectedText, setInjectedText] = useState("");

  // First run: no onboarded flag in localStorage → interview flow over the app.
  const [onboarding, setOnboarding] = useState(false);
  useEffect(() => {
    if (!localStorage.getItem(ONBOARDED_KEY)) setOnboarding(true);
  }, []);

  const { data: watches } = usePolling<Watch[]>(getWatches, 3000, "watches");

  // If the selected watch disappears, fall back to the main chat.
  useEffect(() => {
    if (
      selected !== "main" &&
      watches !== null &&
      !watches.some((w) => w.id === selected)
    ) {
      setSelected("main");
    }
  }, [watches, selected]);

  const selectedWatch =
    selected === "main"
      ? null
      : (watches?.find((w) => w.id === selected) ?? null);

  return (
    <MotionConfig reducedMotion="user">
      <div className="flex h-dvh flex-col">
        {onboarding && <Onboarding onDone={() => setOnboarding(false)} />}
        <OfflineBanner />
        <div className="flex min-h-0 flex-1">
          <Sidebar
            watches={watches}
            selected={selected}
            onSelect={setSelected}
          />
          <ChatPane
            selected={selected}
            watch={selectedWatch}
            injectedText={injectedText}
            onConsumeInjected={() => setInjectedText("")}
          />
          <RightRail
            onFactClick={(path, snippet) => {
              setSelected("main");
              setInjectedText(`About ${path}: ${snippet}`);
            }}
          />
        </div>
      </div>
    </MotionConfig>
  );
}
