"use client";

import { useEffect, useState } from "react";
import { getWatches, type Watch } from "@/lib/api";
import { usePolling } from "@/lib/hooks";
import Sidebar from "@/components/Sidebar";
import ChatPane from "@/components/ChatPane";
import RightRail from "@/components/RightRail";
import OfflineBanner from "@/components/OfflineBanner";

export default function Home() {
  // "main" or a watch id
  const [selected, setSelected] = useState("main");

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
    <div className="flex h-dvh flex-col">
      <OfflineBanner />
      <div className="flex min-h-0 flex-1">
        <Sidebar watches={watches} selected={selected} onSelect={setSelected} />
        <ChatPane selected={selected} watch={selectedWatch} />
        <RightRail />
      </div>
    </div>
  );
}
