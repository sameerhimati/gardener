"use client";

import { useEffect } from "react";
import { motion } from "framer-motion";

/* A short "walking into the garden" flourish played once, after onboarding,
   on the way into the app. Pure SVG + framer-motion so it inherits the moss
   palette and the reduced-motion handling already set by MotionConfig.

   Staging: ground settles → trees grow and sway → sprouts unfurl → a wash of
   light + a few drifting motes → the whole scene lifts away and onDone fires. */

const MOSS = "#587a4e";
const MOSS_DEEP = "#43603b";
const EASE_OUT: [number, number, number, number] = [0.2, 0.7, 0.3, 1];

// one growing tree: trunk draws up, canopy blooms open, then a gentle sway
function Tree({
  x,
  scale,
  delay,
}: {
  x: number;
  scale: number;
  delay: number;
}) {
  return (
    <motion.g
      style={{ originX: `${x}px`, originY: "300px" }}
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: EASE_OUT, delay }}
    >
      {/* trunk */}
      <motion.rect
        x={x - 4 * scale}
        width={8 * scale}
        rx={3}
        fill={MOSS_DEEP}
        initial={{ height: 0, y: 300 }}
        animate={{ height: 70 * scale, y: 300 - 70 * scale }}
        transition={{ duration: 0.5, ease: EASE_OUT, delay }}
      />
      {/* canopy — blooms open, then sways forever (subtle) */}
      <motion.g
        initial={{ scale: 0, opacity: 0 }}
        animate={{
          scale: 1,
          opacity: 1,
          rotate: [0, 1.6, -1.6, 0],
        }}
        transition={{
          scale: { duration: 0.5, ease: EASE_OUT, delay: delay + 0.25 },
          opacity: { duration: 0.5, delay: delay + 0.25 },
          rotate: {
            duration: 4,
            ease: "easeInOut",
            repeat: Infinity,
            delay: delay + 0.7,
          },
        }}
        style={{
          originX: `${x}px`,
          originY: `${300 - 70 * scale}px`,
        }}
      >
        <circle cx={x} cy={300 - 70 * scale} r={34 * scale} fill={MOSS} />
        <circle
          cx={x - 22 * scale}
          cy={300 - 58 * scale}
          r={24 * scale}
          fill={MOSS}
          opacity={0.92}
        />
        <circle
          cx={x + 22 * scale}
          cy={300 - 58 * scale}
          r={24 * scale}
          fill={MOSS}
          opacity={0.92}
        />
        <circle
          cx={x}
          cy={300 - 92 * scale}
          r={26 * scale}
          fill={MOSS}
          opacity={0.96}
        />
      </motion.g>
    </motion.g>
  );
}

// a small sprout that unfurls two leaves out of the ground
function Sprout({ x, delay }: { x: number; delay: number }) {
  return (
    <motion.g
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.3, delay }}
    >
      <motion.path
        d={`M ${x} 300 C ${x - 12} 286, ${x - 16} 278, ${x - 10} 272`}
        stroke={MOSS}
        strokeWidth={3}
        strokeLinecap="round"
        fill="none"
        initial={{ pathLength: 0 }}
        animate={{ pathLength: 1 }}
        transition={{ duration: 0.5, ease: EASE_OUT, delay }}
      />
      <motion.path
        d={`M ${x} 300 C ${x + 12} 288, ${x + 16} 280, ${x + 10} 274`}
        stroke={MOSS}
        strokeWidth={3}
        strokeLinecap="round"
        fill="none"
        initial={{ pathLength: 0 }}
        animate={{ pathLength: 1 }}
        transition={{ duration: 0.5, ease: EASE_OUT, delay: delay + 0.08 }}
      />
      <motion.circle
        cx={x}
        cy={296}
        r={3}
        fill={MOSS_DEEP}
        initial={{ scale: 0 }}
        animate={{ scale: 1 }}
        transition={{ duration: 0.3, delay: delay + 0.2 }}
      />
    </motion.g>
  );
}

export default function GardenEntrance({ onDone }: { onDone: () => void }) {
  // Hold the scene briefly, then hand off to the app.
  useEffect(() => {
    const t = setTimeout(onDone, 2200);
    return () => clearTimeout(t);
  }, [onDone]);

  return (
    <motion.div
      className="fixed inset-0 z-50 flex items-center justify-center overflow-hidden bg-bg"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.3 }}
    >
      {/* the scene lifts up and away on its way out */}
      <motion.div
        className="relative w-full max-w-2xl px-8"
        initial={{ y: 0 }}
        animate={{ y: [0, 0, -18] }}
        transition={{ duration: 2.2, times: [0, 0.8, 1], ease: EASE_OUT }}
      >
        <svg
          viewBox="0 0 520 320"
          className="w-full"
          role="img"
          aria-label="Stepping into your garden"
        >
          {/* soft wash of light rising behind the trees */}
          <motion.ellipse
            cx={260}
            cy={300}
            rx={260}
            ry={120}
            fill={MOSS}
            initial={{ opacity: 0 }}
            animate={{ opacity: 0.07 }}
            transition={{ duration: 1, delay: 0.4 }}
          />

          {/* ground line settling in */}
          <motion.line
            x1={20}
            y1={300}
            x2={500}
            y2={300}
            stroke={MOSS_DEEP}
            strokeWidth={2}
            strokeLinecap="round"
            initial={{ pathLength: 0, opacity: 0 }}
            animate={{ pathLength: 1, opacity: 0.5 }}
            transition={{ duration: 0.6, ease: EASE_OUT }}
          />

          {/* the grove */}
          <Tree x={150} scale={1.1} delay={0.25} />
          <Tree x={370} scale={1.25} delay={0.4} />
          <Tree x={260} scale={0.85} delay={0.55} />

          {/* undergrowth */}
          <Sprout x={95} delay={0.9} />
          <Sprout x={220} delay={1.0} />
          <Sprout x={310} delay={1.05} />
          <Sprout x={440} delay={1.1} />

          {/* a few motes drifting up through the light */}
          {[210, 250, 290, 330].map((x, i) => (
            <motion.circle
              key={x}
              cx={x}
              r={2.5}
              fill={MOSS}
              initial={{ cy: 280, opacity: 0 }}
              animate={{ cy: 180, opacity: [0, 0.7, 0] }}
              transition={{
                duration: 1.6,
                delay: 1 + i * 0.18,
                ease: "easeOut",
              }}
            />
          ))}
        </svg>

        <motion.p
          className="mt-6 text-center text-sm font-medium tracking-tight text-faint"
          initial={{ opacity: 0 }}
          animate={{ opacity: [0, 1, 1, 0] }}
          transition={{ duration: 2.2, times: [0.2, 0.45, 0.8, 1] }}
        >
          Stepping into your garden…
        </motion.p>
      </motion.div>
    </motion.div>
  );
}
