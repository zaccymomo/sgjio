import { useSyncExternalStore } from "react";

/**
 * Sound for lesson decks: a short chime for a right answer, a soft low note for a wrong one,
 * and a tick when a tile lands. Made with the Web Audio API, so there are no sound files to
 * ship or license.
 *
 * One mute switch covers these and the lessons' own audio, and is remembered per browser.
 */

const MUTE_KEY = "sgjio-lesson-muted";
const listeners = new Set<() => void>();

function readMuted(): boolean {
  try {
    return localStorage.getItem(MUTE_KEY) === "1";
  } catch {
    return false;
  }
}

let muted = readMuted();

export function setMuted(value: boolean) {
  muted = value;
  try {
    localStorage.setItem(MUTE_KEY, value ? "1" : "0");
  } catch {
    // Not remembered; the switch still works for this visit.
  }
  listeners.forEach((listener) => listener());
}

export function useMuted(): [boolean, (value: boolean) => void] {
  const value = useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => muted,
    () => false,
  );
  return [value, setMuted];
}

let context: AudioContext | null = null;

function audio(): AudioContext | null {
  if (typeof window === "undefined" || !("AudioContext" in window)) return null;
  context ??= new AudioContext();
  if (context.state === "suspended") void context.resume();
  return context;
}

function note(
  frequency: number,
  start: number,
  length: number,
  type: OscillatorType,
  volume: number,
) {
  const ctx = audio();
  if (!ctx) return;
  const at = ctx.currentTime + start;
  const oscillator = ctx.createOscillator();
  const gain = ctx.createGain();
  oscillator.type = type;
  oscillator.frequency.setValueAtTime(frequency, at);
  gain.gain.setValueAtTime(0.0001, at);
  gain.gain.exponentialRampToValueAtTime(volume, at + 0.015);
  gain.gain.exponentialRampToValueAtTime(0.0001, at + length);
  oscillator.connect(gain).connect(ctx.destination);
  oscillator.start(at);
  oscillator.stop(at + length + 0.05);
}

export function playCorrect() {
  if (muted) return;
  note(880, 0, 0.18, "sine", 0.18);
  note(1318.5, 0.09, 0.32, "sine", 0.16);
}

export function playWrong() {
  if (muted) return;
  note(220, 0, 0.22, "triangle", 0.16);
  note(174.6, 0.12, 0.3, "triangle", 0.14);
}

export function playTick() {
  if (muted) return;
  note(1600, 0, 0.05, "sine", 0.05);
}

export function playFanfare() {
  if (muted) return;
  [523.3, 659.3, 784, 1046.5].forEach((frequency, n) =>
    note(frequency, n * 0.09, 0.4, "sine", 0.12),
  );
}

/** A short buzz on phones that support it; nothing elsewhere. */
export function vibrate(pattern: number | number[]) {
  try {
    navigator.vibrate?.(pattern);
  } catch {
    // Not supported; nothing to do.
  }
}
