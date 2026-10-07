import { Captions, Pause, Play } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { cn } from "../lib/cn";
import { useMuted } from "./sound";
import { tint } from "./tint";
import type { Asset } from "./types";

/**
 * A card's image on a panel tinted with its own colour. The blurred placeholder shows at
 * once, and the image fades in over it once loaded. Images are shown whole (4:3 fills the
 * panel; other shapes get space around them).
 */
export function CardImage({
  asset,
  alt,
  className,
}: {
  asset: Asset | undefined;
  alt: string;
  className?: string;
}) {
  const [loaded, setLoaded] = useState(false);
  return (
    <div
      className={cn("relative aspect-[4/3] w-full overflow-hidden", className)}
      style={{ background: tint(asset?.color) }}
    >
      {asset?.placeholder && (
        <img
          src={asset.placeholder}
          alt=""
          aria-hidden
          className={cn(
            "absolute inset-0 h-full w-full scale-110 object-cover blur-xl transition-opacity duration-500",
            loaded && "opacity-0",
          )}
        />
      )}
      {asset ? (
        <img
          src={asset.url}
          alt={alt}
          draggable={false}
          onLoad={() => setLoaded(true)}
          className={cn(
            "absolute inset-0 h-full w-full object-contain transition-opacity duration-500",
            loaded ? "opacity-100" : "opacity-0",
          )}
        />
      ) : (
        <div className="absolute inset-0 flex items-center justify-center text-xs text-muted">
          Image unavailable
        </div>
      )}
    </div>
  );
}

// --- Audio ---------------------------------------------------------------------------------

const peaksCache = new Map<string, Promise<number[]>>();

/** Loudness of `bars` slices of the file, 0 to 1, worked out once per file in the browser. */
function loadPeaks(url: string, bars: number): Promise<number[]> {
  const key = `${url}#${bars}`;
  let pending = peaksCache.get(key);
  if (!pending) {
    pending = fetch(url)
      .then((response) => response.arrayBuffer())
      .then((data) => new OfflineAudioContext(1, 1, 44100).decodeAudioData(data))
      .then((buffer) => {
        const samples = buffer.getChannelData(0);
        const size = Math.max(1, Math.floor(samples.length / bars));
        const peaks = Array.from({ length: bars }, (_, bar) => {
          let peak = 0;
          for (let i = bar * size; i < (bar + 1) * size && i < samples.length; i += 16) {
            peak = Math.max(peak, Math.abs(samples[i]));
          }
          return peak;
        });
        const loudest = Math.max(...peaks, 0.01);
        return peaks.map((peak) => Math.max(0.12, peak / loudest));
      })
      .catch(() => Array.from({ length: bars }, (_, n) => 0.3 + 0.5 * Math.abs(Math.sin(n * 0.7))));
    peaksCache.set(key, pending);
  }
  return pending;
}

function usePeaks(url: string | undefined, bars: number): number[] | null {
  const [peaks, setPeaks] = useState<number[] | null>(null);
  useEffect(() => {
    if (!url) return;
    let current = true;
    void loadPeaks(url, bars).then((result) => current && setPeaks(result));
    return () => {
      current = false;
    };
  }, [url, bars]);
  return peaks;
}

function seconds(ms: number): string {
  const total = Math.round(ms / 1000);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

function Waveform({
  peaks,
  bars,
  progress,
}: {
  peaks: number[] | null;
  bars: number;
  progress: number;
}) {
  return (
    <span className="flex h-full flex-1 items-center gap-1" aria-hidden>
      {Array.from({ length: bars }, (_, n) => (
        <span
          key={n}
          className={cn(
            "w-full rounded-full transition-[height,background-color] duration-300",
            n / bars < progress ? "bg-brand" : "bg-ink/20",
          )}
          style={{ height: `${Math.round((peaks?.[n] ?? 0.25) * 100)}%` }}
        />
      ))}
    </span>
  );
}

/**
 * A card's audio. Plays by itself when its card opens (`autoplay`), unless sound is muted;
 * the play button always works. "CC" shows the transcript.
 *
 * `size="pill"` sits on top of an image; `size="large"` takes the image's place on a card
 * without one.
 */
export function AudioPlayer({
  asset,
  transcript,
  autoplay,
  size,
  color,
}: {
  asset: Asset | undefined;
  transcript: string;
  autoplay: boolean;
  size: "pill" | "large";
  color?: string | null;
}) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [playing, setPlaying] = useState(false);
  const [progress, setProgress] = useState(0);
  const [showTranscript, setShowTranscript] = useState(false);
  const [muted] = useMuted();
  const bars = size === "pill" ? 20 : 28;
  const peaks = usePeaks(asset?.url, bars);

  useEffect(() => {
    const element = audioRef.current;
    if (!element || !autoplay || muted) return;
    element.currentTime = 0;
    // Browsers refuse until the page has been interacted with; the button still works.
    const timer = setTimeout(() => void element.play().catch(() => {}), 350);
    return () => {
      clearTimeout(timer);
      element.pause();
    };
  }, [autoplay, muted, asset?.url]);

  useEffect(() => {
    const element = audioRef.current;
    if (!element || !playing) return;
    let frame = 0;
    const tick = () => {
      if (element.duration) setProgress(element.currentTime / element.duration);
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [playing]);

  function toggle() {
    const element = audioRef.current;
    if (!element) return;
    if (element.paused) {
      if (element.ended) element.currentTime = 0;
      void element.play().catch(() => {});
    } else {
      element.pause();
    }
  }

  const duration = asset?.duration_ms ?? 0;
  const button = (
    <button
      type="button"
      onClick={(event) => {
        event.stopPropagation();
        toggle();
      }}
      disabled={!asset}
      aria-label={playing ? "Pause audio" : "Play audio"}
      className={cn(
        "flex shrink-0 items-center justify-center rounded-full bg-brand text-white shadow-sm transition-transform hover:scale-105 active:scale-95 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:opacity-50",
        size === "pill" ? "size-9" : "size-16",
      )}
    >
      {playing ? (
        <Pause className={size === "pill" ? "size-4" : "size-7"} fill="currentColor" aria-hidden />
      ) : (
        <Play
          className={cn("translate-x-[1px]", size === "pill" ? "size-4" : "size-7")}
          fill="currentColor"
          aria-hidden
        />
      )}
    </button>
  );
  const captions = transcript && (
    <button
      type="button"
      onClick={(event) => {
        event.stopPropagation();
        setShowTranscript((shown) => !shown);
      }}
      aria-pressed={showTranscript}
      aria-label="Show transcript"
      className={cn(
        "flex size-8 shrink-0 items-center justify-center rounded-full text-muted transition-colors hover:bg-ink/5 hover:text-ink focus-visible:outline-2 focus-visible:outline-brand",
        showTranscript && "bg-ink/10 text-ink",
      )}
    >
      <Captions className="size-4" aria-hidden />
    </button>
  );
  const element = asset && (
    <audio
      ref={audioRef}
      src={asset.url}
      preload="auto"
      onPlay={() => setPlaying(true)}
      onPause={() => setPlaying(false)}
      onEnded={() => {
        setPlaying(false);
        setProgress(1);
      }}
    />
  );

  if (size === "pill") {
    return (
      <div className="flex flex-col gap-1.5">
        <div className="flex h-12 w-full max-w-[17rem] items-center gap-2.5 rounded-full bg-white/90 py-1.5 pr-2 pl-1.5 shadow-md backdrop-blur">
          {button}
          <span className="h-6 flex-1">
            <Waveform peaks={peaks} bars={bars} progress={progress} />
          </span>
          <span className="text-caption font-medium text-muted tabular-nums">
            {seconds(duration)}
          </span>
          {captions}
        </div>
        {showTranscript && (
          <p className="w-fit max-w-[17rem] rounded-xl bg-ink/80 px-3 py-1.5 text-xs text-white backdrop-blur">
            {transcript}
          </p>
        )}
        {element}
      </div>
    );
  }
  return (
    <div
      className="flex aspect-[4/3] w-full flex-col justify-center gap-4 px-6"
      style={{ background: tint(color ?? "#F43F5E", 10) }}
    >
      <div className="flex items-center gap-4">
        {button}
        <span className="h-16 flex-1">
          <Waveform peaks={peaks} bars={bars} progress={progress} />
        </span>
      </div>
      <div className="flex items-center justify-between gap-3">
        <span className="text-xs font-medium text-muted tabular-nums">{seconds(duration)}</span>
        {captions}
      </div>
      {showTranscript && <p className="text-sm text-ink">{transcript}</p>}
      {element}
    </div>
  );
}
